"""
Pipeline Intelligence — Deal Confidence Engine

Binary output: deals you CAN count on vs deals you CANNOT count on.

Priority order for evidence:
  1. Gong call transcripts / AI summaries (PRIMARY — must be near-certain)
  2. HubSpot activity data (SECONDARY — supports or contradicts)

A deal only goes in the "Count On" column if Gong evidence shows 99%+
confidence the buyer is committed. Everything else is "Can't Count On."
"""

import json
import time
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import anthropic
import pandas as pd
import streamlit as st

from main import load_all, AnalyticsData
from src.gong.gong_client import (
    is_gong_configured,
    fetch_gong_enrichment_range,
    map_gong_to_rep,
)
from src.parsing.filters import REPS_IN_SCOPE

MST = ZoneInfo("America/Denver")

st.set_page_config(page_title="Pipeline Intelligence", page_icon="🎯", layout="wide")

# ─── Load data ──────────────────────────────────────────────────────

@st.cache_data(ttl=600, show_spinner="Loading HubSpot data...")
def _load():
    d = load_all()
    return {
        "deals": d.deals,
        "meetings": d.meetings,
        "calls": d.calls,
        "tasks": d.tasks,
        "emails": d.emails,
        "notes": d.notes,
        "tickets": d.tickets,
    }


data = _load()
deals = data["deals"]

# ─── Page header ────────────────────────────────────────────────────

st.title("Pipeline Intelligence")
st.caption(
    "Which deals can you actually count on this quarter? "
    "Gong transcripts are the truth — HubSpot data is secondary."
)

# ─── Sidebar controls ───────────────────────────────────────────────

with st.sidebar:
    st.header("Filters")

    today = date.today()
    q_start_month = ((today.month - 1) // 3) * 3 + 1
    q_start = date(today.year, q_start_month, 1)
    if q_start_month + 3 > 12:
        q_end = date(today.year + 1, (q_start_month + 3) - 12, 1) - timedelta(days=1)
    else:
        q_end = date(today.year, q_start_month + 3, 1) - timedelta(days=1)

    selected_reps = st.multiselect(
        "Reps",
        options=REPS_IN_SCOPE,
        default=REPS_IN_SCOPE,
    )

    st.divider()
    st.header("AI Model")
    MODEL_OPTIONS = {
        "Haiku (fastest, cheapest)": "claude-haiku-4-5-20251001",
        "Sonnet (balanced)": "claude-sonnet-4-20250514",
    }
    model_label = st.selectbox("Model", list(MODEL_OPTIONS.keys()), index=0)
    selected_model = MODEL_OPTIONS[model_label]

    gong_lookback = st.slider(
        "Gong lookback (days)",
        min_value=30, max_value=180, value=90,
        help="How far back to search for Gong calls related to these deals.",
    )

    st.divider()
    gong_ok = is_gong_configured()
    st.caption(f"Gong API: {'✅ Connected' if gong_ok else '❌ Not configured'}")
    st.caption(f"Quarter: {q_start.strftime('%b %d')} – {q_end.strftime('%b %d, %Y')}")
    st.caption(f"Days remaining: {(q_end - today).days}")

# ─── Filter deals ───────────────────────────────────────────────────

if deals.empty:
    st.warning("No deal data loaded. Check Google Sheets connection.")
    st.stop()

# All active deals closing this quarter (any close status — we judge them ourselves)
mask = pd.Series(True, index=deals.index)

if "is_terminal" in deals.columns:
    mask &= ~deals["is_terminal"]

if "close_date" in deals.columns:
    cd = pd.to_datetime(deals["close_date"], errors="coerce")
    mask &= cd.notna() & (cd.dt.date >= q_start) & (cd.dt.date <= q_end)

if "hubspot_owner_name" in deals.columns and selected_reps:
    mask &= deals["hubspot_owner_name"].isin(selected_reps)

forecast_deals = deals[mask].copy()

if forecast_deals.empty:
    st.info(
        f"No active deals with close dates between {q_start} and {q_end}. "
        "Adjust filters in the sidebar."
    )
    st.stop()

if "amount" in forecast_deals.columns:
    forecast_deals = forecast_deals.sort_values("amount", ascending=False)

# ─── Summary metrics ───────────────────────────────────────────────

total_val = forecast_deals["amount"].sum() if "amount" in forecast_deals.columns else 0
n_deals = len(forecast_deals)

col1, col2, col3, col4 = st.columns(4)
col1.metric("Deals This Quarter", f"{n_deals}")
col2.metric("Total Pipeline", f"${total_val:,.0f}")
col3.metric("Quarter Ends", q_end.strftime("%B %d"))
col4.metric("Days Remaining", f"{(q_end - today).days}")

st.divider()


# ─── Retry helper ────────────────────────────────────────────────────

def _call_claude_with_retry(client, model, max_tokens, messages, max_retries=4):
    for attempt in range(max_retries + 1):
        try:
            return client.messages.create(
                model=model, max_tokens=max_tokens, messages=messages,
            )
        except anthropic.RateLimitError:
            if attempt == max_retries:
                raise
            wait = 2 ** (attempt + 1)
            time.sleep(wait)


# ─── Build activity context for a deal ───────────────────────────────

def _get_deal_activity_context(deal_row, all_data, since_date=None):
    """Gather HubSpot activity for a deal by company_name and deal_name."""
    co = str(deal_row.get("company_name", "")).strip().lower()
    dn = str(deal_row.get("deal_name", "")).strip().lower()
    activities = []

    sources = [
        (all_data["emails"], "Email", "activity_date", "email_subject"),
        (all_data["notes"], "Note", "activity_date", "note_body"),
        (all_data["tasks"], "Task", "activity_date", "task_title"),
        (all_data["meetings"], "Meeting", "meeting_start_time", "meeting_name"),
        (all_data["calls"], "Call", "activity_date", "call_outcome"),
    ]

    for df, activity_type, date_col, summary_col in sources:
        if df.empty:
            continue

        df_co = df["company_name"].astype(str).str.strip().str.lower() if "company_name" in df.columns else pd.Series("", index=df.index)
        df_dn = df["deal_name"].astype(str).str.strip().str.lower() if "deal_name" in df.columns else pd.Series("", index=df.index)
        match_mask = ((df_co == co) & (co != "")) | ((df_dn == dn) & (dn != ""))
        matched = df[match_mask]

        if matched.empty:
            continue

        for _, row in matched.iterrows():
            dt = pd.to_datetime(row.get(date_col), errors="coerce")
            if since_date and pd.notna(dt) and dt.date() < since_date:
                continue

            summary = str(row.get(summary_col, ""))[:300]
            if activity_type == "Note":
                import re
                summary = re.sub(r'<[^>]+>', '', summary)

            activities.append({
                "type": activity_type,
                "date": dt.strftime("%Y-%m-%d %H:%M") if pd.notna(dt) else "",
                "owner": str(row.get("hubspot_owner_name", "")),
                "summary": summary,
            })

    activities.sort(key=lambda x: x["date"], reverse=True)
    return activities


# ─── Run the intelligence engine ───────────────────────────────────

if st.button("Run Deal Intelligence", type="primary"):
    if not gong_ok:
        st.error(
            "⚠️ Gong API not configured. This engine REQUIRES Gong call data to make "
            "confidence assessments. Without transcripts, no deal can be marked as 'Count On.' "
            "Add GONG_ACCESS_KEY and GONG_SECRET_KEY to proceed."
        )
        st.stop()

    # Step 1: Fetch Gong calls
    gong_calls_df = pd.DataFrame()
    with st.status("Step 1/3 — Fetching Gong call transcripts...", expanded=True) as status:
        from_dt = datetime(today.year, today.month, today.day, tzinfo=MST) - timedelta(days=gong_lookback)
        to_dt = datetime(today.year, today.month, today.day, 23, 59, 59, tzinfo=MST)

        gong_calls_df = fetch_gong_enrichment_range(
            from_dt, to_dt, include_transcripts=True,
        )
        if not gong_calls_df.empty:
            gong_calls_df["hubspot_owner_name"] = gong_calls_df["gong_user_name"].apply(map_gong_to_rep)
            st.write(f"**{len(gong_calls_df)}** Gong calls found in the last {gong_lookback} days.")
        else:
            st.write("No Gong calls found for this period.")
        status.update(label="Step 1/3 — Gong transcripts fetched", state="complete")

    # Step 2: Match calls to deals and build context
    with st.status("Step 2/3 — Matching calls to deals...", expanded=True) as status:
        deal_contexts = []

        for _, deal in forecast_deals.iterrows():
            deal_co = str(deal.get("company_name", "")).strip().lower()
            deal_name = str(deal.get("deal_name", ""))
            rep = str(deal.get("hubspot_owner_name", ""))
            amount = deal.get("amount", 0)
            stage = str(deal.get("deal_stage", ""))
            close_dt = deal.get("close_date", "")
            close_status = str(deal.get("close_status", ""))

            # Find Gong calls for this company
            matched_calls = []
            if not gong_calls_df.empty and deal_co:
                gong_co = gong_calls_df["company_name"].astype(str).str.strip().str.lower()
                call_mask = gong_co == deal_co
                matched = gong_calls_df[call_mask].copy()
                if not matched.empty:
                    matched["_dt"] = pd.to_datetime(matched["call_start"], errors="coerce")
                    matched = matched.sort_values("_dt", ascending=False)
                    for _, call_row in matched.head(5).iterrows():
                        transcript = call_row.get("transcript_full", "") or call_row.get("transcript_preview", "")
                        matched_calls.append({
                            "call_date": str(call_row.get("call_start", ""))[:10],
                            "call_title": call_row.get("call_title", ""),
                            "rep": call_row.get("gong_user_name", ""),
                            "duration_min": round((call_row.get("call_duration_seconds", 0) or 0) / 60, 1),
                            "topics": call_row.get("topics", ""),
                            "transcript": transcript[:8000] if transcript else "",
                        })

            # HubSpot activity (last 90 days)
            lookback_date = today - timedelta(days=90)
            hs_activity = _get_deal_activity_context(deal, data, since_date=lookback_date)

            deal_contexts.append({
                "deal_name": deal_name,
                "company": str(deal.get("company_name", "")),
                "rep": rep,
                "amount": float(amount) if pd.notna(amount) else 0,
                "stage": stage,
                "close_date": str(close_dt)[:10] if pd.notna(close_dt) else "",
                "close_status": close_status,
                "pipeline": str(deal.get("pipeline", "")),
                "gong_calls": matched_calls,
                "hubspot_activity": hs_activity[:20],
            })

        n_with_gong = sum(1 for d in deal_contexts if d["gong_calls"])
        n_without = len(deal_contexts) - n_with_gong
        st.write(
            f"**{n_with_gong}** deals matched to Gong calls. "
            f"**{n_without}** deals have NO Gong data (auto-classified as Can't Count On)."
        )
        status.update(label="Step 2/3 — Context built", state="complete")

    # Step 3: AI analysis — binary classification
    with st.status("Step 3/3 — AI confidence analysis...", expanded=True) as status:
        client = anthropic.Anthropic()
        all_results = []

        # Deals WITHOUT Gong calls → automatic "Can't Count On"
        no_gong_deals = [d for d in deal_contexts if not d["gong_calls"]]
        for ctx in no_gong_deals:
            all_results.append({
                "deal_name": ctx["deal_name"],
                "company": ctx["company"],
                "rep": ctx["rep"],
                "amount": ctx["amount"],
                "verdict": "CANT_COUNT_ON",
                "confidence": 0.0,
                "reason": "No Gong call data available. Cannot verify buyer commitment without conversation evidence.",
                "key_quote": None,
                "risk_factors": ["No recorded calls with this prospect in the lookback period"],
                "next_step": "Get on a call with this prospect ASAP and confirm timeline, budget, and decision process.",
                "gong_calls_found": 0,
                "last_contact": "",
            })

        # Deals WITH Gong calls → AI analysis
        gong_deals = [d for d in deal_contexts if d["gong_calls"]]
        BATCH = 3
        progress = st.progress(0, text="Analyzing deals with Gong data...")

        for i in range(0, len(gong_deals), BATCH):
            batch = gong_deals[i : i + BATCH]

            deals_block = ""
            for ctx in batch:
                gong_section = "GONG CALL TRANSCRIPTS (most recent first):\n"
                for c in ctx["gong_calls"]:
                    gong_section += f"""
  Call: {c['call_title']} ({c['call_date']}, {c['duration_min']} min, rep: {c['rep']})
  Topics: {c['topics']}
  Transcript:
  {c['transcript']}
  ---
"""

                hs_section = ""
                if ctx["hubspot_activity"]:
                    hs_section = "HUBSPOT ACTIVITY (secondary context, last 90 days):\n"
                    for a in ctx["hubspot_activity"][:15]:
                        hs_section += f"  [{a['type']}] {a['date']} | {a['owner']} | {a['summary']}\n"

                deals_block += f"""
============================
DEAL: {ctx['deal_name']}
COMPANY: {ctx['company']}
REP: {ctx['rep']}
AMOUNT: ${ctx['amount']:,.0f}
STAGE: {ctx['stage']}
HUBSPOT CLOSE STATUS: {ctx['close_status']}
CLOSE DATE: {ctx['close_date']}
PIPELINE: {ctx['pipeline']}

{gong_section}
{hs_section}
============================

"""

            prompt = f"""You are a ruthlessly honest deal analyst for Calyx Containers (cannabis packaging). Today is {today.strftime('%B %d, %Y')}. The quarter ends {q_end.strftime('%B %d, %Y')} ({(q_end - today).days} days remaining).

Your job: decide if each deal is one the company can TRULY COUNT ON closing this quarter, or NOT.

THE STANDARD IS EXTREMELY HIGH. A deal is "COUNT ON" ONLY if:
- The Gong call transcript contains CLEAR, EXPLICIT buyer commitment language
- Examples: confirmed PO timeline, verbal agreement on pricing, stated decision date, "we're moving forward", approved budget, signed LOI
- The buyer (not the rep) said these things
- There is recent activity (within last 2-3 weeks) showing continued momentum
- There are NO contradicting signals (ghosting, competitor mentions, budget concerns, pushed timelines)

A deal is "CAN'T COUNT ON" if ANY of these are true:
- No clear buyer commitment language in transcripts
- Last meaningful contact was more than 3 weeks ago
- Buyer expressed hesitation, budget concerns, or competitor evaluation
- Only the rep is expressing confidence — the buyer hasn't confirmed
- The deal stage or activity doesn't support the close date
- Vague language like "we're interested" or "let's circle back" — that's not commitment

HubSpot data is SECONDARY. It can support or contradict Gong evidence but cannot alone make a deal "COUNT ON."
If HubSpot shows activity AFTER the last Gong call that changes the picture, note it.

For each deal return JSON:
{{
  "deal_name": "...",
  "verdict": "COUNT_ON" or "CANT_COUNT_ON",
  "confidence": 0.0 to 1.0 (your confidence in THIS VERDICT),
  "reason": "2-3 sentences. Be specific. Quote what the buyer actually said.",
  "key_quote": "The single most important thing the buyer said (exact quote from transcript), or null if nothing definitive",
  "risk_factors": ["list of specific concerns"],
  "next_step": "One specific action the rep should take this week"
}}

Analyze these deals:
{deals_block}

Return a JSON array. No preamble, no markdown fences."""

            try:
                response = _call_claude_with_retry(
                    client, selected_model, 4000,
                    [{"role": "user", "content": prompt}],
                )
                raw = response.content[0].text.strip()
                if raw.startswith("```"):
                    raw = raw.split("```")[1]
                    if raw.startswith("json"):
                        raw = raw[4:]
                raw = raw.strip()
                batch_results = json.loads(raw)
                if isinstance(batch_results, dict):
                    batch_results = [batch_results]

                # Enrich with metadata
                for br in batch_results:
                    ctx_match = next((c for c in batch if c["deal_name"] == br.get("deal_name")), None)
                    if ctx_match:
                        br["company"] = ctx_match["company"]
                        br["rep"] = ctx_match["rep"]
                        br["amount"] = ctx_match["amount"]
                        br["gong_calls_found"] = len(ctx_match["gong_calls"])

                    # ENFORCE: only COUNT_ON if confidence >= 0.99
                    if br.get("verdict") == "COUNT_ON" and br.get("confidence", 0) < 0.99:
                        br["verdict"] = "CANT_COUNT_ON"
                        br["reason"] = (
                            f"Downgraded: AI confidence was {br.get('confidence', 0):.0%}, "
                            f"below the 99% threshold. Original assessment: {br.get('reason', '')}"
                        )

                all_results.extend(batch_results)
            except Exception as e:
                st.warning(f"Batch {i // BATCH + 1} failed: {e}")
                for ctx in batch:
                    all_results.append({
                        "deal_name": ctx["deal_name"],
                        "company": ctx["company"],
                        "rep": ctx["rep"],
                        "amount": ctx["amount"],
                        "verdict": "CANT_COUNT_ON",
                        "confidence": 0,
                        "reason": f"Analysis failed: {e}",
                        "key_quote": None,
                        "risk_factors": ["Analysis error — manual review needed"],
                        "next_step": "Manual review needed",
                        "gong_calls_found": 0,
                    })

            if gong_deals:
                progress.progress(
                    min((i + BATCH) / len(gong_deals), 1.0),
                    text=f"Analyzed {min(i + BATCH, len(gong_deals))}/{len(gong_deals)} deals...",
                )
            time.sleep(2)

        progress.empty()
        status.update(label="Step 3/3 — Analysis complete", state="complete")

    # ─── Display results ──────────────────────────────────────────────

    st.divider()

    count_on = [r for r in all_results if r.get("verdict") == "COUNT_ON"]
    cant_count_on = [r for r in all_results if r.get("verdict") != "COUNT_ON"]

    count_on_val = sum(r.get("amount", 0) for r in count_on)
    cant_count_on_val = sum(r.get("amount", 0) for r in cant_count_on)

    # ─── Top-level verdict ────────────────────────────────────────────

    st.markdown("---")

    c1, c2, c3 = st.columns([2, 1, 2])
    with c1:
        st.markdown(
            f"### ✅ Count On: {len(count_on)} deals\n"
            f"### ${count_on_val:,.0f}"
        )
    with c2:
        st.markdown("### vs")
    with c3:
        st.markdown(
            f"### ❌ Can't Count On: {len(cant_count_on)} deals\n"
            f"### ${cant_count_on_val:,.0f}"
        )

    st.markdown("---")

    # ─── COUNT ON section ─────────────────────────────────────────────

    st.subheader("✅ Deals You Can Count On")
    st.caption("99%+ confidence based on Gong call evidence. The buyer has committed.")

    if not count_on:
        st.info(
            "No deals meet the 99% confidence threshold based on Gong transcript evidence. "
            "This is honest — better to know now than miss forecast."
        )
    else:
        for r in sorted(count_on, key=lambda x: x.get("amount", 0), reverse=True):
            with st.expander(
                f"✅ **{r['deal_name']}** — {r.get('company', '')} — "
                f"${r.get('amount', 0):,.0f} — {r.get('rep', '')}",
                expanded=True,
            ):
                st.markdown(f"**Confidence:** {r.get('confidence', 0):.0%}")
                st.markdown(f"**Why this counts:** {r.get('reason', '')}")

                quote = r.get("key_quote")
                if quote:
                    st.success(f"**Buyer said:** \"{quote}\"")

                next_step = r.get("next_step", "")
                if next_step:
                    st.markdown(f"**Next step:** {next_step}")

                risks = r.get("risk_factors", [])
                if risks:
                    st.markdown("**Watch for:**")
                    for risk in risks:
                        st.caption(f"  ⚠️ {risk}")

    st.markdown("---")

    # ─── CAN'T COUNT ON section ───────────────────────────────────────

    st.subheader("❌ Deals You Can't Count On")
    st.caption(
        "These may still close, but the evidence isn't there yet. "
        "Don't build your forecast around them."
    )

    # Sub-group: has Gong data but didn't pass the bar
    has_gong_but_failed = [r for r in cant_count_on if r.get("gong_calls_found", 0) > 0]
    no_gong = [r for r in cant_count_on if r.get("gong_calls_found", 0) == 0]

    if has_gong_but_failed:
        st.markdown("#### Calls recorded, but buyer hasn't committed")
        for r in sorted(has_gong_but_failed, key=lambda x: x.get("amount", 0), reverse=True):
            with st.expander(
                f"⚠️ **{r['deal_name']}** — {r.get('company', '')} — "
                f"${r.get('amount', 0):,.0f} — {r.get('rep', '')}",
                expanded=False,
            ):
                st.markdown(f"**Confidence:** {r.get('confidence', 0):.0%}")
                st.markdown(f"**Why it's not bankable:** {r.get('reason', '')}")

                quote = r.get("key_quote")
                if quote:
                    st.warning(f"**Buyer said:** \"{quote}\"")

                risks = r.get("risk_factors", [])
                if risks:
                    st.markdown("**Risk factors:**")
                    for risk in risks:
                        st.error(risk)

                next_step = r.get("next_step", "")
                if next_step:
                    st.markdown(f"**To convert this deal:** {next_step}")

    if no_gong:
        st.markdown("#### No Gong calls — flying blind")
        for r in sorted(no_gong, key=lambda x: x.get("amount", 0), reverse=True):
            with st.expander(
                f"🔇 **{r['deal_name']}** — {r.get('company', '')} — "
                f"${r.get('amount', 0):,.0f} — {r.get('rep', '')}",
                expanded=False,
            ):
                st.error("No recorded Gong calls for this company. Can't verify buyer intent.")
                st.markdown(f"**Action:** {r.get('next_step', 'Get on a call with this prospect.')}")

    # ─── Download CSV ─────────────────────────────────────────────────
    st.divider()
    rows_out = []
    for r in all_results:
        rows_out.append({
            "Deal": r.get("deal_name", ""),
            "Company": r.get("company", ""),
            "Rep": r.get("rep", ""),
            "Amount": r.get("amount", 0),
            "Verdict": "Count On" if r.get("verdict") == "COUNT_ON" else "Can't Count On",
            "Confidence": r.get("confidence", 0),
            "Reason": r.get("reason", ""),
            "Key Buyer Quote": r.get("key_quote", ""),
            "Risk Factors": " | ".join(r.get("risk_factors", [])),
            "Next Step": r.get("next_step", ""),
            "Gong Calls Found": r.get("gong_calls_found", 0),
        })
    csv_out = pd.DataFrame(rows_out).to_csv(index=False)
    st.download_button(
        "Download Intelligence Report (CSV)",
        data=csv_out,
        file_name=f"deal_intelligence_{today.isoformat()}.csv",
        mime="text/csv",
    )
