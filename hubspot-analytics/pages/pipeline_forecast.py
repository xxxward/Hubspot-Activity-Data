"""
Pipeline Intelligence — Deal Confidence Engine

Binary output: deals you CAN count on vs deals you CANNOT count on.

Evidence priority:
  1. Gong call transcripts / AI summaries (PRIMARY signal)
  2. HubSpot activity data (emails, meetings, notes, tasks — SECONDARY signal)

Both sources feed into the AI analysis. Gong carries more weight because
it's what the buyer actually said, but HubSpot activity (meeting frequency,
email recency, deal stage progression) matters too.
"""

import json
import re
import time
from datetime import date, datetime, timedelta
from difflib import SequenceMatcher
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
    "Gong transcripts + HubSpot activity analyzed together."
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

    close_status_filter = st.multiselect(
        "Close Status",
        options=["Expect", "Best Case", "Opportunity"],
        default=["Expect"],
        help="Filter deals by HubSpot close status. Start with Expect for the tightest view.",
    )

    selected_reps = st.multiselect(
        "Reps",
        options=REPS_IN_SCOPE,
        default=REPS_IN_SCOPE,
    )

    st.divider()
    st.header("AI Model")
    MODEL_OPTIONS = {
        "Sonnet (recommended)": "claude-sonnet-4-20250514",
        "Haiku (faster, less accurate)": "claude-haiku-4-5-20251001",
    }
    model_label = st.selectbox("Model", list(MODEL_OPTIONS.keys()), index=0)
    selected_model = MODEL_OPTIONS[model_label]

    confidence_threshold = st.slider(
        "Confidence threshold (%)",
        min_value=50, max_value=99, value=75,
        help="Minimum AI confidence to classify a deal as 'Count On'. "
             "75% is recommended — high enough to be meaningful, low enough to surface real deals.",
    )

    gong_lookback = st.slider(
        "Gong lookback (days)",
        min_value=30, max_value=180, value=90,
        help="How far back to search for Gong calls related to these deals.",
    )

    st.divider()
    gong_ok = is_gong_configured()
    st.caption(f"Gong API: {'✅ Connected' if gong_ok else '⚠️ Not configured (HubSpot-only mode)'}")
    st.caption(f"Quarter: {q_start.strftime('%b %d')} – {q_end.strftime('%b %d, %Y')}")
    st.caption(f"Days remaining: {(q_end - today).days}")


# ─── Fuzzy company matching ─────────────────────────────────────────

def _normalize_company(name: str) -> str:
    """Normalize company name for matching: lowercase, strip suffixes, punctuation."""
    name = str(name).strip().lower()
    # Remove common suffixes
    for suffix in (" llc", " inc", " inc.", " corp", " corp.", " co.", " co",
                   " ltd", " ltd.", " limited", " company", " group"):
        if name.endswith(suffix):
            name = name[: -len(suffix)].strip()
    # Remove punctuation
    name = re.sub(r"[^a-z0-9\s]", "", name)
    # Collapse whitespace
    name = re.sub(r"\s+", " ", name).strip()
    return name


def _fuzzy_match_company(deal_co: str, gong_companies: pd.Series, threshold: float = 0.65) -> pd.Series:
    """
    Return a boolean mask of Gong rows that match the deal company name.
    Uses exact-normalized match first, then falls back to fuzzy matching.
    """
    norm_deal = _normalize_company(deal_co)
    if not norm_deal:
        return pd.Series(False, index=gong_companies.index)

    norm_gong = gong_companies.apply(_normalize_company)

    # Exact normalized match
    exact_mask = norm_gong == norm_deal

    # Contains match (either direction)
    contains_mask = norm_gong.apply(
        lambda g: norm_deal in g or g in norm_deal if g else False
    )

    # Fuzzy match for remaining
    fuzzy_mask = norm_gong.apply(
        lambda g: SequenceMatcher(None, norm_deal, g).ratio() >= threshold if g else False
    )

    return exact_mask | contains_mask | fuzzy_mask


# ─── Filter deals ───────────────────────────────────────────────────

if deals.empty:
    st.warning("No deal data loaded. Check Google Sheets connection.")
    st.stop()

mask = pd.Series(True, index=deals.index)

if "is_terminal" in deals.columns:
    mask &= ~deals["is_terminal"]

if "close_date" in deals.columns:
    cd = pd.to_datetime(deals["close_date"], errors="coerce")
    mask &= cd.notna() & (cd.dt.date >= q_start) & (cd.dt.date <= q_end)

if "close_status" in deals.columns and close_status_filter:
    mask &= deals["close_status"].isin(close_status_filter)

if "hubspot_owner_name" in deals.columns and selected_reps:
    mask &= deals["hubspot_owner_name"].isin(selected_reps)

forecast_deals = deals[mask].copy()

if forecast_deals.empty:
    st.info(
        f"No active {', '.join(close_status_filter)} deals with close dates "
        f"between {q_start} and {q_end}. Adjust filters in the sidebar."
    )
    st.stop()

if "amount" in forecast_deals.columns:
    forecast_deals = forecast_deals.sort_values("amount", ascending=False)

# ─── Summary metrics ───────────────────────────────────────────────

total_val = forecast_deals["amount"].sum() if "amount" in forecast_deals.columns else 0
n_deals = len(forecast_deals)

col1, col2, col3, col4 = st.columns(4)
col1.metric("Deals in Scope", f"{n_deals}")
col2.metric("Total Pipeline", f"${total_val:,.0f}")
col3.metric("Quarter Ends", q_end.strftime("%B %d"))
col4.metric("Days Remaining", f"{(q_end - today).days}")

# Show the deal table
st.divider()
display_cols = [c for c in (
    "deal_name", "company_name", "hubspot_owner_name", "amount",
    "deal_stage", "close_status", "close_date", "pipeline",
) if c in forecast_deals.columns]

with st.expander(f"View all {n_deals} deals in scope", expanded=False):
    st.dataframe(
        forecast_deals[display_cols].reset_index(drop=True),
        use_container_width=True,
        hide_index=True,
    )

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

    # Step 1: Fetch Gong calls (if configured)
    gong_calls_df = pd.DataFrame()
    if gong_ok:
        with st.status("Step 1/3 — Fetching Gong call transcripts...", expanded=True) as status:
            from_dt = datetime(today.year, today.month, today.day, tzinfo=MST) - timedelta(days=gong_lookback)
            to_dt = datetime(today.year, today.month, today.day, 23, 59, 59, tzinfo=MST)

            gong_calls_df = fetch_gong_enrichment_range(
                from_dt, to_dt, include_transcripts=True,
            )
            if not gong_calls_df.empty:
                gong_calls_df["hubspot_owner_name"] = gong_calls_df["gong_user_name"].apply(map_gong_to_rep)
                st.write(f"**{len(gong_calls_df)}** Gong calls found in the last {gong_lookback} days.")

                # Show unique companies in Gong for debugging
                gong_companies = gong_calls_df["company_name"].dropna().unique()
                st.write(f"Gong calls span **{len(gong_companies)}** unique companies.")
            else:
                st.write("No Gong calls found for this period.")
            status.update(label="Step 1/3 — Gong transcripts fetched", state="complete")
    else:
        st.info(
            "Gong API not configured — analyzing with HubSpot data only. "
            "Add GONG_ACCESS_KEY and GONG_SECRET_KEY for transcript-based analysis."
        )

    # Step 2: Match calls to deals and build context
    with st.status("Step 2/3 — Building deal context (Gong + HubSpot)...", expanded=True) as status:
        deal_contexts = []

        for _, deal in forecast_deals.iterrows():
            deal_co = str(deal.get("company_name", "")).strip()
            deal_name = str(deal.get("deal_name", ""))
            rep = str(deal.get("hubspot_owner_name", ""))
            amount = deal.get("amount", 0)
            stage = str(deal.get("deal_stage", ""))
            close_dt = deal.get("close_date", "")
            close_status = str(deal.get("close_status", ""))

            # Find Gong calls — fuzzy match on company name
            matched_calls = []
            if not gong_calls_df.empty and deal_co:
                gong_co_series = gong_calls_df["company_name"].astype(str)
                call_mask = _fuzzy_match_company(deal_co, gong_co_series)
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
                            "gong_company": call_row.get("company_name", ""),
                        })

            # HubSpot activity (last 90 days)
            lookback_date = today - timedelta(days=90)
            hs_activity = _get_deal_activity_context(deal, data, since_date=lookback_date)

            deal_contexts.append({
                "deal_name": deal_name,
                "company": deal_co,
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
        n_with_hs = sum(1 for d in deal_contexts if d["hubspot_activity"])
        n_neither = sum(1 for d in deal_contexts if not d["gong_calls"] and not d["hubspot_activity"])
        st.write(
            f"**{n_with_gong}** deals matched to Gong calls (fuzzy match). "
            f"**{n_with_hs}** deals have HubSpot activity. "
            f"**{n_neither}** deals have no data at all."
        )
        status.update(label="Step 2/3 — Context built", state="complete")

    # Step 3: AI analysis — ALL deals get analyzed
    with st.status("Step 3/3 — AI confidence analysis...", expanded=True) as status:
        client = anthropic.Anthropic()
        all_results = []
        BATCH = 3
        total_deals = len(deal_contexts)
        progress = st.progress(0, text="Analyzing deals...")

        for i in range(0, total_deals, BATCH):
            batch = deal_contexts[i : i + BATCH]

            deals_block = ""
            for ctx in batch:
                # Build Gong section
                if ctx["gong_calls"]:
                    gong_section = f"GONG CALL TRANSCRIPTS ({len(ctx['gong_calls'])} calls, most recent first):\n"
                    for c in ctx["gong_calls"]:
                        gong_section += f"""
  Call: {c['call_title']} ({c['call_date']}, {c['duration_min']} min, rep: {c['rep']})
  Gong Company: {c.get('gong_company', '')}
  Topics: {c['topics']}
  Transcript:
  {c['transcript']}
  ---
"""
                else:
                    gong_section = "NO GONG CALLS FOUND for this company.\n"

                # Build HubSpot section
                if ctx["hubspot_activity"]:
                    hs_section = f"HUBSPOT ACTIVITY ({len(ctx['hubspot_activity'])} items, last 90 days, most recent first):\n"
                    for a in ctx["hubspot_activity"][:15]:
                        hs_section += f"  [{a['type']}] {a['date']} | {a['owner']} | {a['summary']}\n"
                else:
                    hs_section = "NO HUBSPOT ACTIVITY found in the last 90 days.\n"

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

            prompt = f"""You are a deal analyst for Calyx Containers, a cannabis packaging company. Today is {today.strftime('%B %d, %Y')}. The quarter ends {q_end.strftime('%B %d, %Y')} ({(q_end - today).days} days remaining).

Your job: decide if each deal will ACTUALLY close this quarter based on the evidence.

EVIDENCE HIERARCHY:
1. GONG TRANSCRIPTS (primary) — what the buyer actually said on calls. This is the strongest signal.
   Look for: verbal commitments, agreed timelines, approved budgets, PO discussions, "we're moving forward", pricing agreements
   Red flags: "we need to think about it", "checking with my team", competitor mentions, budget concerns, silence

2. HUBSPOT ACTIVITY (secondary) — emails, meetings, notes, tasks. Shows engagement momentum.
   Strong signals: recent meetings (last 2 weeks), email exchanges about contracts/pricing/onboarding, multiple touchpoints
   Weak signals: only outbound emails from rep with no response, stale activity (nothing in 3+ weeks), only automated tasks

CLASSIFICATION:
- "COUNT_ON": Strong evidence the deal will close. Gong transcripts show buyer commitment OR HubSpot shows active deal progression with concrete next steps. You need to be genuinely confident.
- "CANT_COUNT_ON": Evidence is weak, mixed, or missing. Don't guess — if you're not confident, say so.

IMPORTANT:
- Be honest but not impossibly strict. If a buyer verbally agreed to pricing and there's a follow-up meeting scheduled, that's COUNT_ON.
- If there's strong HubSpot activity but no Gong calls, you CAN still mark it COUNT_ON if the activity clearly shows deal progression (e.g., contract sent, pricing confirmed via email, onboarding scheduled).
- If there's literally no data (no Gong calls AND no HubSpot activity), it's CANT_COUNT_ON.
- Your confidence score should reflect how sure you are. 0.9 = very likely. 0.7 = probable. 0.5 = coin flip.

For each deal return JSON:
{{
  "deal_name": "...",
  "verdict": "COUNT_ON" or "CANT_COUNT_ON",
  "confidence": 0.0 to 1.0,
  "evidence_source": "gong" or "hubspot" or "both" or "none",
  "reason": "2-3 sentences. Be specific. Reference actual evidence — quote buyer language from transcripts or cite specific HubSpot activity dates.",
  "key_quote": "Exact buyer quote from Gong transcript if available, or most telling HubSpot activity detail. null if nothing substantive.",
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
                        br["hs_activity_count"] = len(ctx_match["hubspot_activity"])

                    # Enforce confidence threshold
                    conf = br.get("confidence", 0)
                    if br.get("verdict") == "COUNT_ON" and conf < (confidence_threshold / 100):
                        br["verdict"] = "CANT_COUNT_ON"
                        br["reason"] = (
                            f"Below {confidence_threshold}% threshold (AI confidence: {conf:.0%}). "
                            f"{br.get('reason', '')}"
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
                        "evidence_source": "none",
                        "reason": f"Analysis failed: {e}",
                        "key_quote": None,
                        "risk_factors": ["Analysis error — manual review needed"],
                        "next_step": "Manual review needed",
                        "gong_calls_found": len(ctx["gong_calls"]),
                        "hs_activity_count": len(ctx["hubspot_activity"]),
                    })

            progress.progress(
                min((i + BATCH) / total_deals, 1.0),
                text=f"Analyzed {min(i + BATCH, total_deals)}/{total_deals} deals...",
            )
            time.sleep(1)

        progress.empty()
        status.update(label="Step 3/3 — Analysis complete", state="complete")

    # ─── Display results ──────────────────────────────────────────────

    st.divider()

    count_on = [r for r in all_results if r.get("verdict") == "COUNT_ON"]
    cant_count_on = [r for r in all_results if r.get("verdict") != "COUNT_ON"]

    count_on_val = sum(r.get("amount", 0) for r in count_on)
    cant_count_on_val = sum(r.get("amount", 0) for r in cant_count_on)

    # ─── Top-level verdict ────────────────────────────────────────────

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

    st.caption(f"Confidence threshold: {confidence_threshold}% | Model: {model_label}")

    st.markdown("---")

    # ─── COUNT ON section ─────────────────────────────────────────────

    st.subheader("✅ Deals You Can Count On")
    st.caption(
        f"AI confidence >= {confidence_threshold}% based on Gong transcripts and/or HubSpot activity."
    )

    if not count_on:
        st.info(
            f"No deals met the {confidence_threshold}% confidence threshold. "
            "Try lowering the threshold in the sidebar, or review the 'Can't Count On' deals for ones that are close."
        )
    else:
        for r in sorted(count_on, key=lambda x: x.get("amount", 0), reverse=True):
            evidence_tag = r.get("evidence_source", "").upper()
            confidence_pct = r.get("confidence", 0)
            with st.expander(
                f"✅ **{r['deal_name']}** — {r.get('company', '')} — "
                f"${r.get('amount', 0):,.0f} — {r.get('rep', '')} "
                f"({confidence_pct:.0%} | {evidence_tag})",
                expanded=True,
            ):
                st.markdown(f"**Confidence:** {confidence_pct:.0%} | **Evidence:** {evidence_tag}")
                st.markdown(f"**Why this counts:** {r.get('reason', '')}")

                quote = r.get("key_quote")
                if quote:
                    st.success(f"**Key evidence:** \"{quote}\"")

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
    st.caption("Insufficient evidence to forecast with confidence. May still close — just can't bank on it.")

    # Sort by amount descending so biggest at-risk deals show first
    cant_count_on_sorted = sorted(cant_count_on, key=lambda x: x.get("amount", 0), reverse=True)

    for r in cant_count_on_sorted:
        evidence_tag = r.get("evidence_source", "none").upper()
        confidence_pct = r.get("confidence", 0)
        gong_count = r.get("gong_calls_found", 0)
        hs_count = r.get("hs_activity_count", 0)
        data_label = f"Gong: {gong_count} | HS: {hs_count}"

        with st.expander(
            f"❌ **{r['deal_name']}** — {r.get('company', '')} — "
            f"${r.get('amount', 0):,.0f} — {r.get('rep', '')} "
            f"({confidence_pct:.0%} | {data_label})",
            expanded=False,
        ):
            st.markdown(f"**Confidence:** {confidence_pct:.0%} | **Evidence:** {evidence_tag} | **Data:** {data_label}")
            st.markdown(f"**Why it's not bankable:** {r.get('reason', '')}")

            quote = r.get("key_quote")
            if quote:
                st.warning(f"**Key signal:** \"{quote}\"")

            risks = r.get("risk_factors", [])
            if risks:
                st.markdown("**Risk factors:**")
                for risk in risks:
                    st.error(risk)

            next_step = r.get("next_step", "")
            if next_step:
                st.markdown(f"**To convert this deal:** {next_step}")

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
            "Evidence Source": r.get("evidence_source", ""),
            "Reason": r.get("reason", ""),
            "Key Quote": r.get("key_quote", ""),
            "Risk Factors": " | ".join(r.get("risk_factors", [])),
            "Next Step": r.get("next_step", ""),
            "Gong Calls Found": r.get("gong_calls_found", 0),
            "HubSpot Activities": r.get("hs_activity_count", 0),
        })
    csv_out = pd.DataFrame(rows_out).to_csv(index=False)
    st.download_button(
        "Download Intelligence Report (CSV)",
        data=csv_out,
        file_name=f"deal_intelligence_{today.isoformat()}.csv",
        mime="text/csv",
    )
