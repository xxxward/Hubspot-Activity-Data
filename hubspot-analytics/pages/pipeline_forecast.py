"""
Pipeline Forecast — End-of-Quarter Deal Intelligence

Priority order:
  1. EXPECT deals with close date this quarter
  2. For each deal, find Gong calls (by company name) and pull transcripts
  3. Claude reads transcripts and answers: will this deal close? Quote exact phrases.
  4. Layer in HubSpot activity (emails, notes, tasks) as secondary context
  5. Surface a clear forecast: Closing / At Risk / Unlikely
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

st.set_page_config(page_title="Pipeline Forecast", page_icon="🔮", layout="wide")

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

st.title("Pipeline Forecast")
st.caption(
    "Analyze Expect deals closing this quarter. Gong transcripts first, "
    "then HubSpot activity for the full picture."
)

# ─── Sidebar controls ───────────────────────────────────────────────

with st.sidebar:
    st.header("Forecast Filters")

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
        help="Expect = highest confidence. Add Best Case or Opportunity for a wider view.",
    )

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
    st.caption(f"Gong API: {'Connected' if gong_ok else 'Not configured'}")
    st.caption(f"Current quarter: {q_start.strftime('%b %d')} – {q_end.strftime('%b %d, %Y')}")

# ─── Filter deals ───────────────────────────────────────────────────

if deals.empty:
    st.warning("No deal data loaded. Check Google Sheets connection.")
    st.stop()

# Filter to active deals closing this quarter with selected close status
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

# Sort by amount descending
if "amount" in forecast_deals.columns:
    forecast_deals = forecast_deals.sort_values("amount", ascending=False)

# ─── Display deal summary ───────────────────────────────────────────

total_val = forecast_deals["amount"].sum() if "amount" in forecast_deals.columns else 0
n_deals = len(forecast_deals)

col1, col2, col3, col4 = st.columns(4)
col1.metric("Deals in Scope", f"{n_deals}")
col2.metric("Total Pipeline", f"${total_val:,.0f}")
col3.metric("Quarter Ends", q_end.strftime("%B %d"))
col4.metric("Days Remaining", f"{(q_end - today).days}")

st.divider()

# Show the deal table
display_cols = [c for c in (
    "deal_name", "company_name", "hubspot_owner_name", "amount",
    "deal_stage", "close_status", "close_date", "pipeline",
) if c in forecast_deals.columns]

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
    """
    Gather HubSpot activity (emails, notes, tasks, meetings, calls)
    for a deal, matched by company_name and deal_name.
    Returns a list of activity dicts sorted by date descending.
    """
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

        # Match on company_name or deal_name
        df_co = df["company_name"].astype(str).str.strip().str.lower() if "company_name" in df.columns else pd.Series("", index=df.index)
        df_dn = df["deal_name"].astype(str).str.strip().str.lower() if "deal_name" in df.columns else pd.Series("", index=df.index)
        mask = ((df_co == co) & (co != "")) | ((df_dn == dn) & (dn != ""))
        matched = df[mask]

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

            owner = row.get("hubspot_owner_name", "")

            activities.append({
                "type": activity_type,
                "date": dt.strftime("%Y-%m-%d %H:%M") if pd.notna(dt) else "",
                "owner": str(owner),
                "summary": summary,
            })

    activities.sort(key=lambda x: x["date"], reverse=True)
    return activities


# ─── Run the forecast analysis ───────────────────────────────────────

if st.button("Run Pipeline Forecast", type="primary"):
    if not gong_ok:
        st.warning(
            "Gong API not configured. Analysis will use HubSpot activity only "
            "(no call transcripts). Add GONG_ACCESS_KEY and GONG_SECRET_KEY for full analysis."
        )

    # Step 1: Fetch Gong calls for the lookback period
    gong_calls_df = pd.DataFrame()
    if gong_ok:
        with st.status("Step 1/3 — Fetching Gong calls...", expanded=True) as status:
            from_dt = datetime(today.year, today.month, today.day, tzinfo=MST) - timedelta(days=gong_lookback)
            to_dt = datetime(today.year, today.month, today.day, 23, 59, 59, tzinfo=MST)

            gong_calls_df = fetch_gong_enrichment_range(
                from_dt, to_dt, include_transcripts=True,
            )
            if not gong_calls_df.empty:
                gong_calls_df["hubspot_owner_name"] = gong_calls_df["gong_user_name"].apply(map_gong_to_rep)
                st.write(f"Found **{len(gong_calls_df)}** Gong calls in the last {gong_lookback} days.")
            else:
                st.write("No Gong calls found for this period.")
            status.update(label="Step 1/3 — Gong calls fetched", state="complete")
    else:
        st.info("Skipping Gong (not configured). Using HubSpot activity only.")

    # Step 2: Match Gong calls to deals by company name
    with st.status("Step 2/3 — Matching calls to deals & building context...", expanded=True) as status:
        deal_contexts = []

        for _, deal in forecast_deals.iterrows():
            deal_co = str(deal.get("company_name", "")).strip().lower()
            deal_name = str(deal.get("deal_name", ""))
            rep = str(deal.get("hubspot_owner_name", ""))
            amount = deal.get("amount", 0)
            stage = str(deal.get("deal_stage", ""))
            close_dt = deal.get("close_date", "")

            # Find Gong calls for this company
            matched_calls = []
            if not gong_calls_df.empty and deal_co:
                gong_co = gong_calls_df["company_name"].astype(str).str.strip().str.lower()
                call_mask = gong_co == deal_co
                matched = gong_calls_df[call_mask].copy()
                if not matched.empty:
                    # Sort by date descending, take most recent calls
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

            # Get HubSpot activity context (last 90 days)
            lookback_date = today - timedelta(days=90)
            hs_activity = _get_deal_activity_context(deal, data, since_date=lookback_date)

            deal_contexts.append({
                "deal_name": deal_name,
                "company": str(deal.get("company_name", "")),
                "rep": rep,
                "amount": float(amount) if pd.notna(amount) else 0,
                "stage": stage,
                "close_date": str(close_dt)[:10] if pd.notna(close_dt) else "",
                "close_status": str(deal.get("close_status", "")),
                "pipeline": str(deal.get("pipeline", "")),
                "gong_calls": matched_calls,
                "hubspot_activity": hs_activity[:20],  # Cap at 20 most recent
            })

        n_with_gong = sum(1 for d in deal_contexts if d["gong_calls"])
        st.write(
            f"Matched **{n_with_gong}/{len(deal_contexts)}** deals to Gong calls. "
            f"All {len(deal_contexts)} deals have HubSpot activity context."
        )
        status.update(label="Step 2/3 — Context built", state="complete")

    # Step 3: Claude analysis — batch deals for analysis
    with st.status("Step 3/3 — AI forecast analysis...", expanded=True) as status:
        client = anthropic.Anthropic()
        all_forecasts = []
        BATCH = 3  # deals per API call to manage tokens
        progress = st.progress(0, text="Analyzing deals...")

        for i in range(0, len(deal_contexts), BATCH):
            batch = deal_contexts[i : i + BATCH]

            deals_block = ""
            for ctx in batch:
                # Build Gong section
                gong_section = ""
                if ctx["gong_calls"]:
                    gong_section = "GONG CALL TRANSCRIPTS (most recent first):\n"
                    for c in ctx["gong_calls"]:
                        gong_section += f"""
  Call: {c['call_title']} ({c['call_date']}, {c['duration_min']} min, rep: {c['rep']})
  Topics: {c['topics']}
  Transcript:
  {c['transcript']}
  ---
"""
                else:
                    gong_section = "NO GONG CALLS FOUND for this company.\n"

                # Build HubSpot activity section
                hs_section = ""
                if ctx["hubspot_activity"]:
                    hs_section = "HUBSPOT ACTIVITY (last 90 days, most recent first):\n"
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
CLOSE STATUS: {ctx['close_status']}
CLOSE DATE: {ctx['close_date']}
PIPELINE: {ctx['pipeline']}

{gong_section}
{hs_section}
============================

"""

            prompt = f"""You are a VP of Sales analyst for Calyx Containers, a cannabis packaging company. It is {today.strftime('%B %d, %Y')}. The quarter ends {q_end.strftime('%B %d, %Y')} ({(q_end - today).days} days remaining).

Analyze each deal below and predict whether it will close THIS QUARTER.

CRITICAL INSTRUCTIONS:
- The Gong call transcript is the PRIMARY evidence. What the customer ACTUALLY SAID matters most.
- Quote the exact phrases from the transcript that indicate deal momentum or risk.
- HubSpot activity (emails, notes, tasks) is SECONDARY context that supports or contradicts the call evidence.
- If there's recent activity AFTER the last Gong call that changes the picture (e.g., an email saying "we're going with someone else"), flag that.
- Be honest and direct. Sales forecasts are only useful when they're accurate.

For each deal, return a JSON object with:
{{
  "deal_name": "...",
  "forecast": "CLOSING" or "AT RISK" or "UNLIKELY" or "INSUFFICIENT DATA",
  "confidence": 0.0 to 1.0,
  "reasoning": "2-3 sentence explanation",
  "key_evidence": ["exact quote from transcript or activity that supports your forecast"],
  "risk_factors": ["specific concerns"],
  "recommended_action": "what the rep should do this week",
  "last_meaningful_contact": "date and type of most recent substantive interaction"
}}

Here are the deals to analyze:
{deals_block}

Return a JSON array with one object per deal. No preamble, no markdown fences."""

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
                all_forecasts.extend(batch_results)
            except Exception as e:
                st.warning(f"Batch {i // BATCH + 1} failed: {e}")
                for ctx in batch:
                    all_forecasts.append({
                        "deal_name": ctx["deal_name"],
                        "forecast": "ERROR",
                        "confidence": 0,
                        "reasoning": f"Analysis failed: {e}",
                        "key_evidence": [],
                        "risk_factors": [],
                        "recommended_action": "Manual review needed",
                        "last_meaningful_contact": "",
                    })

            progress.progress(
                min((i + BATCH) / len(deal_contexts), 1.0),
                text=f"Analyzed {min(i + BATCH, len(deal_contexts))}/{len(deal_contexts)} deals...",
            )
            time.sleep(2)

        progress.empty()
        status.update(label="Step 3/3 — Forecast complete", state="complete")

    # ─── Display results ──────────────────────────────────────────────

    st.divider()
    st.subheader("Pipeline Forecast Results")

    # Summary metrics
    closing = [f for f in all_forecasts if f.get("forecast") == "CLOSING"]
    at_risk = [f for f in all_forecasts if f.get("forecast") == "AT RISK"]
    unlikely = [f for f in all_forecasts if f.get("forecast") == "UNLIKELY"]
    no_data = [f for f in all_forecasts if f.get("forecast") in ("INSUFFICIENT DATA", "ERROR")]

    # Match amounts back to forecasts
    deal_amount_map = {}
    for _, d in forecast_deals.iterrows():
        deal_amount_map[str(d.get("deal_name", ""))] = float(d.get("amount", 0)) if pd.notna(d.get("amount")) else 0

    closing_val = sum(deal_amount_map.get(f["deal_name"], 0) for f in closing)
    at_risk_val = sum(deal_amount_map.get(f["deal_name"], 0) for f in at_risk)
    unlikely_val = sum(deal_amount_map.get(f["deal_name"], 0) for f in unlikely)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Likely Closing", f"{len(closing)} deals", f"${closing_val:,.0f}")
    c2.metric("At Risk", f"{len(at_risk)} deals", f"${at_risk_val:,.0f}")
    c3.metric("Unlikely", f"{len(unlikely)} deals", f"${unlikely_val:,.0f}")
    c4.metric("Need Data", f"{len(no_data)} deals")

    st.divider()

    # Render each deal forecast
    FORECAST_COLORS = {
        "CLOSING": ("#052e16", "#4ade80", "🟢"),
        "AT RISK": ("#422006", "#fbbf24", "🟡"),
        "UNLIKELY": ("#450a0a", "#f87171", "🔴"),
        "INSUFFICIENT DATA": ("#1e1b4b", "#818cf8", "🔵"),
        "ERROR": ("#1c1917", "#a8a29e", "⚫"),
    }

    # Sort: UNLIKELY first (needs attention), then AT RISK, then CLOSING
    sort_order = {"UNLIKELY": 0, "AT RISK": 1, "INSUFFICIENT DATA": 2, "ERROR": 3, "CLOSING": 4}
    all_forecasts.sort(key=lambda f: sort_order.get(f.get("forecast", ""), 5))

    for fc in all_forecasts:
        forecast_type = fc.get("forecast", "ERROR")
        bg, text_color, icon = FORECAST_COLORS.get(forecast_type, FORECAST_COLORS["ERROR"])
        deal_name = fc.get("deal_name", "Unknown")
        amount = deal_amount_map.get(deal_name, 0)
        confidence = fc.get("confidence", 0)

        with st.expander(
            f"{icon} **{deal_name}** — ${amount:,.0f} — {forecast_type} ({confidence:.0%} confidence)",
            expanded=(forecast_type in ("UNLIKELY", "AT RISK")),
        ):
            st.markdown(f"**Forecast:** {forecast_type} ({confidence:.0%} confidence)")
            st.markdown(f"**Reasoning:** {fc.get('reasoning', '')}")

            evidence = fc.get("key_evidence", [])
            if evidence:
                st.markdown("**Key Evidence:**")
                for ev in evidence:
                    st.markdown(f"> _{ev}_")

            risks = fc.get("risk_factors", [])
            if risks:
                st.markdown("**Risk Factors:**")
                for r in risks:
                    st.warning(r)

            action = fc.get("recommended_action", "")
            if action:
                st.markdown(f"**Recommended Action:** {action}")

            last_contact = fc.get("last_meaningful_contact", "")
            if last_contact:
                st.caption(f"Last meaningful contact: {last_contact}")

    # Download CSV
    st.divider()
    rows_out = []
    for fc in all_forecasts:
        rows_out.append({
            "Deal": fc.get("deal_name", ""),
            "Amount": deal_amount_map.get(fc.get("deal_name", ""), 0),
            "Forecast": fc.get("forecast", ""),
            "Confidence": fc.get("confidence", 0),
            "Reasoning": fc.get("reasoning", ""),
            "Key Evidence": " | ".join(fc.get("key_evidence", [])),
            "Risk Factors": " | ".join(fc.get("risk_factors", [])),
            "Recommended Action": fc.get("recommended_action", ""),
        })
    csv_out = pd.DataFrame(rows_out).to_csv(index=False)
    st.download_button(
        "Download Forecast as CSV",
        data=csv_out,
        file_name=f"pipeline_forecast_{today.isoformat()}.csv",
        mime="text/csv",
    )
