"""
Pipeline Intelligence — Deal Confidence Engine

Evidence sources (all from Google Sheets, no API calls):
  1. Gong AI Summaries (primary — what the buyer said, AI-analyzed)
  2. HubSpot activity data (emails, meetings, notes — secondary)
  3. Gong call metadata (topics, trackers, duration)

Matches Gong calls to deals by company name (fuzzy matching),
then uses the AI summary data + HubSpot activity to assess confidence.
"""

import re
import time
from datetime import date, datetime, timedelta
from difflib import SequenceMatcher

import pandas as pd
import streamlit as st

from main import load_all, AnalyticsData
from src.parsing.filters import REPS_IN_SCOPE

st.set_page_config(page_title="Pipeline Intelligence", page_icon="🎯", layout="wide")

# ─── Load data ──────────────────────────────────────────────────────

@st.cache_data(ttl=600, show_spinner="Loading data...")
def _load():
    d = load_all()
    return {f: getattr(d, f) for f in d.__dataclass_fields__}


raw = _load()
data = AnalyticsData(**raw)
deals = data.deals

# ─── Page header ────────────────────────────────────────────────────

st.title("Pipeline Intelligence")
st.caption(
    "Which deals can you actually count on this quarter? "
    "Gong AI summaries + HubSpot activity analyzed together."
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
    )

    selected_reps = st.multiselect(
        "Reps",
        options=REPS_IN_SCOPE,
        default=REPS_IN_SCOPE,
    )

    st.divider()
    st.caption(f"Quarter: {q_start.strftime('%b %d')} – {q_end.strftime('%b %d, %Y')}")
    st.caption(f"Days remaining: {(q_end - today).days}")
    st.caption(f"Gong AI Summaries: {len(data.gong_ai_summaries)} calls")
    st.caption(f"Gong Calls: {len(data.gong_calls)} calls")


# ─── Fuzzy company matching ─────────────────────────────────────────

def _normalize_company(name: str) -> str:
    name = str(name).strip().lower()
    for suffix in (" llc", " inc", " inc.", " corp", " corp.", " co.", " co",
                   " ltd", " ltd.", " limited", " company", " group"):
        if name.endswith(suffix):
            name = name[: -len(suffix)].strip()
    name = re.sub(r"[^a-z0-9\s]", "", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name


def _fuzzy_match_company(deal_co: str, gong_companies: pd.Series, threshold: float = 0.65) -> pd.Series:
    norm_deal = _normalize_company(deal_co)
    if not norm_deal:
        return pd.Series(False, index=gong_companies.index)

    norm_gong = gong_companies.apply(_normalize_company)
    exact_mask = norm_gong == norm_deal
    contains_mask = norm_gong.apply(
        lambda g: norm_deal in g or g in norm_deal if g else False
    )
    fuzzy_mask = norm_gong.apply(
        lambda g: SequenceMatcher(None, norm_deal, g).ratio() >= threshold if g else False
    )
    return exact_mask | contains_mask | fuzzy_mask


# ─── Filter deals ───────────────────────────────────────────────────

if deals.empty:
    st.warning("No deal data loaded.")
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
    st.info(f"No active {', '.join(close_status_filter)} deals closing this quarter.")
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

with st.expander(f"View all {n_deals} deals", expanded=False):
    display_cols = [c for c in (
        "deal_name", "company_name", "hubspot_owner_name", "amount",
        "deal_stage", "close_status", "close_date", "pipeline",
    ) if c in forecast_deals.columns]
    st.dataframe(forecast_deals[display_cols].reset_index(drop=True),
                 use_container_width=True, hide_index=True)

st.divider()


# ─── Build activity context ─────────────────────────────────────────

def _get_deal_activity_context(deal_row, all_data, since_date=None):
    co = str(deal_row.get("company_name", "")).strip().lower()
    dn = str(deal_row.get("deal_name", "")).strip().lower()
    activities = []

    sources = [
        (all_data.emails, "Email", "activity_date", "email_subject"),
        (all_data.notes, "Note", "activity_date", "note_body"),
        (all_data.meetings, "Meeting", "meeting_start_time", "meeting_name"),
        (all_data.calls, "Call", "activity_date", "call_outcome"),
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
                "date": dt.strftime("%Y-%m-%d") if pd.notna(dt) else "",
                "owner": str(row.get("hubspot_owner_name", "")),
                "summary": summary,
            })

    activities.sort(key=lambda x: x["date"], reverse=True)
    return activities


# ─── Match Gong data to deals ───────────────────────────────────────

if st.button("Run Deal Intelligence", type="primary"):

    gong_summaries = data.gong_ai_summaries.copy()
    gong_calls_sheet = data.gong_calls.copy()

    with st.status("Matching Gong calls to deals & building context...", expanded=True) as status:
        deal_contexts = []

        # Determine the company column in Gong data
        # AI Summaries might have "external_participants" but not a clean company name
        # Gong Calls might have it in external_participants or CRM associations
        # We'll try to match on external participants or title keywords

        for _, deal in forecast_deals.iterrows():
            deal_co = str(deal.get("company_name", "")).strip()
            deal_name = str(deal.get("deal_name", ""))
            rep = str(deal.get("hubspot_owner_name", ""))
            amount = deal.get("amount", 0)
            stage = str(deal.get("deal_stage", ""))
            close_dt = deal.get("close_date", "")
            close_status = str(deal.get("close_status", ""))

            # Match Gong AI Summaries by external_participants or title
            matched_summaries = []
            if not gong_summaries.empty and deal_co:
                # Try matching on external_participants (often contains company/contact info)
                ext_col = "external_participants" if "external_participants" in gong_summaries.columns else None
                title_col = "title" if "title" in gong_summaries.columns else None

                match_mask = pd.Series(False, index=gong_summaries.index)
                if ext_col:
                    match_mask |= _fuzzy_match_company(deal_co, gong_summaries[ext_col].astype(str))
                if title_col:
                    match_mask |= _fuzzy_match_company(deal_co, gong_summaries[title_col].astype(str))

                matched = gong_summaries[match_mask].copy()
                if not matched.empty:
                    date_col = "date" if "date" in matched.columns else None
                    if date_col:
                        matched[date_col] = pd.to_datetime(matched[date_col], errors="coerce")
                        matched = matched.sort_values(date_col, ascending=False)
                    for _, row in matched.head(5).iterrows():
                        matched_summaries.append({
                            "date": str(row.get("date", ""))[:10],
                            "title": row.get("title", ""),
                            "rep": row.get("rep_name", ""),
                            "summary": row.get("brief_summary", "") or "",
                            "key_points": row.get("key_points", "") or "",
                            "highlights": row.get("highlights", "") or "",
                            "outcome": row.get("call_outcome", "") or "",
                            "topics": row.get("topics", "") or "",
                            "trackers": row.get("trackers_fired", "") or "",
                        })

            # HubSpot activity
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
                "gong_summaries": matched_summaries,
                "hubspot_activity": hs_activity[:20],
            })

        n_with_gong = sum(1 for d in deal_contexts if d["gong_summaries"])
        n_with_hs = sum(1 for d in deal_contexts if d["hubspot_activity"])
        st.write(
            f"**{n_with_gong}** deals matched to Gong calls. "
            f"**{n_with_hs}** deals have HubSpot activity. "
        )
        status.update(label="Context built", state="complete")

    # ─── Score deals based on evidence ────────────────────────────────
    # No Claude API needed — score based on data signals directly

    with st.status("Scoring deals...", expanded=True) as status:
        all_results = []

        for ctx in deal_contexts:
            gong_count = len(ctx["gong_summaries"])
            hs_count = len(ctx["hubspot_activity"])
            confidence = 0.0
            reasons = []
            risk_factors = []
            key_evidence = None
            evidence_source = "none"

            # --- Gong signal scoring ---
            if gong_count > 0:
                evidence_source = "gong"
                confidence += 0.3  # Base: has Gong calls
                confidence += min(gong_count * 0.1, 0.2)  # More calls = more signal

                most_recent = ctx["gong_summaries"][0]
                summary_text = (most_recent.get("summary", "") + " " + most_recent.get("key_points", "")).lower()
                key_evidence = most_recent.get("summary", "") or most_recent.get("key_points", "")

                # Positive signals in AI summary
                positive_signals = [
                    "moving forward", "approved", "purchase order", "agreed",
                    "confirmed", "onboarding", "contract", "signed", "ready to go",
                    "let's do it", "next steps", "pricing accepted", "budget approved",
                    "decision made", "go ahead", "place the order", "samples approved",
                ]
                neg_signals = [
                    "not ready", "competitor", "budget concern", "hold off",
                    "need to think", "circle back", "not interested", "too expensive",
                    "delay", "pushed", "on hold", "reconsidering", "ghosting",
                ]

                pos_hits = [s for s in positive_signals if s in summary_text]
                neg_hits = [s for s in neg_signals if s in summary_text]

                if pos_hits:
                    confidence += min(len(pos_hits) * 0.1, 0.3)
                    reasons.append(f"Positive signals in Gong summary: {', '.join(pos_hits[:3])}")
                if neg_hits:
                    confidence -= min(len(neg_hits) * 0.15, 0.3)
                    risk_factors.extend([f"Gong flagged: \"{s}\"" for s in neg_hits[:3]])

                # Check recency of last Gong call
                last_date_str = most_recent.get("date", "")
                if last_date_str:
                    try:
                        last_date = datetime.strptime(last_date_str[:10], "%Y-%m-%d").date()
                        days_since = (today - last_date).days
                        if days_since <= 14:
                            confidence += 0.1
                            reasons.append(f"Recent Gong call ({days_since} days ago)")
                        elif days_since > 30:
                            confidence -= 0.1
                            risk_factors.append(f"Last Gong call was {days_since} days ago")
                    except (ValueError, TypeError):
                        pass

                # Outcome check
                outcome = most_recent.get("outcome", "").lower()
                if outcome and any(w in outcome for w in ("positive", "next steps", "follow up")):
                    confidence += 0.05

            # --- HubSpot signal scoring ---
            if hs_count > 0:
                if evidence_source == "gong":
                    evidence_source = "both"
                else:
                    evidence_source = "hubspot"
                    confidence += 0.2  # Base: has HubSpot activity

                confidence += min(hs_count * 0.02, 0.15)  # More activity = more signal

                # Check recency
                if ctx["hubspot_activity"]:
                    most_recent_hs = ctx["hubspot_activity"][0]
                    hs_date_str = most_recent_hs.get("date", "")
                    if hs_date_str:
                        try:
                            hs_date = datetime.strptime(hs_date_str[:10], "%Y-%m-%d").date()
                            days_since_hs = (today - hs_date).days
                            if days_since_hs <= 7:
                                confidence += 0.1
                                reasons.append(f"Active in HubSpot ({days_since_hs} days ago)")
                            elif days_since_hs > 21:
                                risk_factors.append(f"No HubSpot activity in {days_since_hs} days")
                        except (ValueError, TypeError):
                            pass

                # Activity mix
                types = [a["type"] for a in ctx["hubspot_activity"]]
                if "Meeting" in types:
                    confidence += 0.05
                    reasons.append(f"{types.count('Meeting')} meetings logged")

            # --- No data ---
            if gong_count == 0 and hs_count == 0:
                risk_factors.append("No Gong calls or HubSpot activity found")
                reasons.append("No evidence available to assess this deal")

            # --- Close status boost ---
            if ctx["close_status"] == "Expect":
                confidence += 0.05  # Small boost for Expect status

            # Clamp confidence
            confidence = max(0.0, min(confidence, 0.99))

            # Determine verdict
            verdict = "COUNT_ON" if confidence >= 0.60 else "CANT_COUNT_ON"

            all_results.append({
                "deal_name": ctx["deal_name"],
                "company": ctx["company"],
                "rep": ctx["rep"],
                "amount": ctx["amount"],
                "stage": ctx["stage"],
                "close_status": ctx["close_status"],
                "verdict": verdict,
                "confidence": confidence,
                "evidence_source": evidence_source,
                "reason": " | ".join(reasons) if reasons else "Insufficient evidence",
                "key_evidence": key_evidence,
                "risk_factors": risk_factors,
                "gong_calls_found": gong_count,
                "hs_activity_count": hs_count,
            })

        status.update(label="Scoring complete", state="complete")

    # ─── Display results ──────────────────────────────────────────────

    st.divider()

    count_on = [r for r in all_results if r["verdict"] == "COUNT_ON"]
    cant_count_on = [r for r in all_results if r["verdict"] != "COUNT_ON"]

    count_on_val = sum(r.get("amount", 0) for r in count_on)
    cant_count_on_val = sum(r.get("amount", 0) for r in cant_count_on)

    c1, c2, c3 = st.columns([2, 1, 2])
    with c1:
        st.markdown(
            f"### Count On: {len(count_on)} deals\n"
            f"### ${count_on_val:,.0f}"
        )
    with c2:
        st.markdown("### vs")
    with c3:
        st.markdown(
            f"### Can't Count On: {len(cant_count_on)} deals\n"
            f"### ${cant_count_on_val:,.0f}"
        )

    st.markdown("---")

    # ─── COUNT ON section ─────────────────────────────────────────────
    st.subheader("Deals You Can Count On")
    st.caption("Strong evidence from Gong calls and/or HubSpot activity.")

    if not count_on:
        st.info("No deals met the confidence threshold based on available evidence.")
    else:
        for r in sorted(count_on, key=lambda x: x.get("amount", 0), reverse=True):
            src = r.get("evidence_source", "").upper()
            conf = r.get("confidence", 0)
            with st.expander(
                f"**{r['deal_name']}** — {r.get('company', '')} — "
                f"${r.get('amount', 0):,.0f} — {r.get('rep', '')} "
                f"({conf:.0%} | {src})",
                expanded=True,
            ):
                st.markdown(f"**Confidence:** {conf:.0%} | **Evidence:** {src}")
                st.markdown(f"**Why:** {r.get('reason', '')}")
                ev = r.get("key_evidence")
                if ev and str(ev).strip():
                    st.success(f"**Gong summary:** {ev[:500]}")
                risks = r.get("risk_factors", [])
                if risks:
                    for risk in risks:
                        st.caption(f"  Warning: {risk}")

    st.markdown("---")

    # ─── CAN'T COUNT ON section ───────────────────────────────────────
    st.subheader("Deals You Can't Count On")
    st.caption("Insufficient evidence — may still close but can't bank on it.")

    for r in sorted(cant_count_on, key=lambda x: x.get("amount", 0), reverse=True):
        src = r.get("evidence_source", "none").upper()
        conf = r.get("confidence", 0)
        gong_n = r.get("gong_calls_found", 0)
        hs_n = r.get("hs_activity_count", 0)

        with st.expander(
            f"**{r['deal_name']}** — {r.get('company', '')} — "
            f"${r.get('amount', 0):,.0f} — {r.get('rep', '')} "
            f"({conf:.0%} | Gong:{gong_n} HS:{hs_n})",
            expanded=False,
        ):
            st.markdown(f"**Confidence:** {conf:.0%} | **Evidence:** {src}")
            st.markdown(f"**Why not bankable:** {r.get('reason', '')}")
            ev = r.get("key_evidence")
            if ev and str(ev).strip():
                st.warning(f"**Gong summary:** {ev[:500]}")
            risks = r.get("risk_factors", [])
            if risks:
                for risk in risks:
                    st.error(risk)

    # ─── Download CSV ─────────────────────────────────────────────────
    st.divider()
    rows_out = []
    for r in all_results:
        rows_out.append({
            "Deal": r.get("deal_name", ""),
            "Company": r.get("company", ""),
            "Rep": r.get("rep", ""),
            "Amount": r.get("amount", 0),
            "Stage": r.get("stage", ""),
            "Close Status": r.get("close_status", ""),
            "Verdict": "Count On" if r.get("verdict") == "COUNT_ON" else "Can't Count On",
            "Confidence": r.get("confidence", 0),
            "Evidence Source": r.get("evidence_source", ""),
            "Reason": r.get("reason", ""),
            "Key Evidence": r.get("key_evidence", ""),
            "Risk Factors": " | ".join(r.get("risk_factors", [])),
            "Gong Calls": r.get("gong_calls_found", 0),
            "HubSpot Activities": r.get("hs_activity_count", 0),
        })
    csv_out = pd.DataFrame(rows_out).to_csv(index=False)
    st.download_button(
        "Download Intelligence Report (CSV)",
        data=csv_out,
        file_name=f"deal_intelligence_{today.isoformat()}.csv",
        mime="text/csv",
    )
