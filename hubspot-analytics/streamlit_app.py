"""
HubSpot Sales Analytics Dashboard

Tab 1: Rep Activity Scoreboard
  - KPI cards, leaderboard, by-rep chart, daily trend

Tab 2: Deal Health Monitor
  - Active deals per rep, joined to activity by company_name
  - Health signals: Green/Yellow/Red based on recency of activity
  - Flag deals in Best Case/Commit with no recent activity
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import date, timedelta, datetime

from src.utils.logging import setup_logging
from src.parsing.filters import REPS_IN_SCOPE, PIPELINES_IN_SCOPE
from src.metrics.scoring import WEIGHTS
from main import load_all, AnalyticsData

setup_logging()

st.set_page_config(page_title="HubSpot Sales Analytics", page_icon="\U0001f4ca", layout="wide")

# -- Data Loading ---------------------------------------------------------

@st.cache_data(ttl=600, show_spinner="Loading data from Google Sheets...")
def get_data() -> dict:
    data = load_all()
    return {f: getattr(data, f) for f in data.__dataclass_fields__}

try:
    _d = get_data()
    data = AnalyticsData(**_d)
except Exception as e:
    st.error(f"**Data load failed:** {e}")
    st.info("Verify your Streamlit secrets and that the sheet is shared with the service account email.")
    st.stop()


# -- Sidebar Filters -------------------------------------------------------

st.sidebar.title("Filters")

_default_start = date.today() - timedelta(days=7)
date_range = st.sidebar.date_input(
    "Date Range",
    value=(_default_start, date.today()),
    max_value=date.today(),
)
start_date, end_date = (
    date_range if isinstance(date_range, tuple) and len(date_range) == 2
    else (_default_start, date.today())
)

selected_reps = st.sidebar.multiselect("Sales Reps", REPS_IN_SCOPE, default=REPS_IN_SCOPE)
selected_pipelines = st.sidebar.multiselect("Pipelines", PIPELINES_IN_SCOPE, default=PIPELINES_IN_SCOPE)
show_debug = st.sidebar.checkbox("Show Debug Info", value=False)


# -- Filter helpers --------------------------------------------------------

def _frep(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "hubspot_owner_name" not in df.columns:
        return df
    return df.loc[df["hubspot_owner_name"].isin(selected_reps)].copy()

def _fpipe(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "pipeline" not in df.columns:
        return df
    return df.loc[df["pipeline"].isin(selected_pipelines)].copy()

def _fdate_raw(df: pd.DataFrame, date_col: str = "activity_date") -> pd.DataFrame:
    """Filter raw activity DataFrame by date range."""
    if df.empty:
        return df
    for col in (date_col, "activity_date", "meeting_start_time", "created_date"):
        if col in df.columns:
            dt = pd.to_datetime(df[col], errors="coerce")
            valid = dt.notna()
            dt_date = dt.dt.date
            mask = valid & (dt_date >= start_date) & (dt_date <= end_date)
            return df.loc[mask].copy()
    return df

def _fdate(df: pd.DataFrame, col: str = "period_day") -> pd.DataFrame:
    if df.empty or col not in df.columns:
        return df
    dt = pd.to_datetime(df[col], errors="coerce").dt.date
    return df.loc[(dt >= start_date) & (dt <= end_date)].copy()


# -- Leaderboard builder ---------------------------------------------------

def _compute_leaderboard(meetings, calls, tasks):
    rows = []
    for rep in selected_reps:
        m_count = len(meetings[meetings["hubspot_owner_name"] == rep]) if not meetings.empty and "hubspot_owner_name" in meetings.columns else 0
        c_count = len(calls[calls["hubspot_owner_name"] == rep]) if not calls.empty and "hubspot_owner_name" in calls.columns else 0

        comp, overdue = 0, 0
        if not tasks.empty and "hubspot_owner_name" in tasks.columns:
            rep_tasks = tasks[tasks["hubspot_owner_name"] == rep]
            status_col = "task_status" if "task_status" in rep_tasks.columns else None
            if status_col and not rep_tasks.empty:
                upper = rep_tasks[status_col].astype(str).str.upper().str.strip()
                comp = int(upper.isin({"COMPLETED", "COMPLETE", "DONE"}).sum())
                overdue = int(upper.isin({"OVERDUE", "PAST_DUE", "DEFERRED"}).sum())
                if "due_date" in rep_tasks.columns:
                    past_due = pd.to_datetime(rep_tasks["due_date"], errors="coerce") < pd.Timestamp.now()
                    not_done = ~upper.isin({"COMPLETED", "COMPLETE", "DONE"})
                    overdue = max(overdue, int((past_due & not_done).sum()))

        score = (m_count * WEIGHTS["meetings"] + c_count * WEIGHTS["calls"] +
                 comp * WEIGHTS["completed_tasks"] + overdue * WEIGHTS["overdue_tasks"])
        rows.append({
            "Rep": rep, "Meetings": m_count, "Calls": c_count,
            "Completed Tasks": comp, "Overdue Tasks": overdue, "Activity Score": score,
        })
    return pd.DataFrame(rows).sort_values("Activity Score", ascending=False).reset_index(drop=True)


# -- Deal health builder ---------------------------------------------------

def _build_deal_health(deals, meetings, calls, tasks):
    """
    Join active deals to activity data by company_name.
    Returns a DataFrame with one row per deal + activity summary.
    """
    if deals.empty:
        return pd.DataFrame()

    # Get active (non-terminal) deals
    active = deals.copy()
    if "is_terminal" in active.columns:
        active = active[~active["is_terminal"]]
    if active.empty:
        return pd.DataFrame()

    # Combine all activity with company + date
    activity_frames = []
    for df, atype, dcol in [
        (calls, "Call", "activity_date"),
        (meetings, "Meeting", "meeting_start_time"),
        (tasks, "Task", "completed_at"),
    ]:
        if df.empty or "company_name" not in df.columns:
            continue
        tmp = df[["company_name", dcol]].copy() if dcol in df.columns else df[["company_name"]].copy()
        if dcol in tmp.columns:
            tmp["activity_date_parsed"] = pd.to_datetime(tmp[dcol], errors="coerce")
        else:
            tmp["activity_date_parsed"] = pd.NaT
        tmp["activity_type"] = atype
        activity_frames.append(tmp[["company_name", "activity_date_parsed", "activity_type"]])

    if not activity_frames:
        # No activity data — return deals with empty activity columns
        active["last_activity_date"] = pd.NaT
        active["activity_count_30d"] = 0
        active["health"] = "No Activity"
        return active

    all_activity = pd.concat(activity_frames, ignore_index=True)
    all_activity = all_activity.dropna(subset=["company_name"])
    all_activity["company_name_clean"] = all_activity["company_name"].astype(str).str.strip().str.lower()

    # Build per-company activity summary
    now = pd.Timestamp.now()
    day7 = now - pd.Timedelta(days=7)
    day30 = now - pd.Timedelta(days=30)

    company_summary = (
        all_activity.groupby("company_name_clean")
        .agg(
            last_activity=("activity_date_parsed", "max"),
            total_activities=("activity_date_parsed", "count"),
            activities_7d=("activity_date_parsed", lambda x: (x >= day7).sum()),
            activities_30d=("activity_date_parsed", lambda x: (x >= day30).sum()),
            calls=("activity_type", lambda x: (x == "Call").sum()),
            meetings=("activity_type", lambda x: (x == "Meeting").sum()),
            tasks=("activity_type", lambda x: (x == "Task").sum()),
        )
        .reset_index()
    )

    # Join to deals
    active = active.copy()
    active["company_name_clean"] = active["company_name"].astype(str).str.strip().str.lower() if "company_name" in active.columns else ""

    merged = active.merge(company_summary, on="company_name_clean", how="left")

    # Fill NaN for deals with no matching activity
    for col in ["last_activity", "total_activities", "activities_7d", "activities_30d", "calls", "meetings", "tasks"]:
        if col in merged.columns:
            merged[col] = merged[col].fillna(0) if col != "last_activity" else merged[col]

    # Health status
    def _health(row):
        last = row.get("last_activity")
        if pd.isna(last):
            return "No Activity"
        if last >= day7:
            return "Active"
        if last >= day30:
            return "Stale"
        return "Inactive"

    merged["health"] = merged.apply(_health, axis=1)

    # Days since last activity
    merged["days_since_activity"] = merged["last_activity"].apply(
        lambda x: (now - x).days if pd.notna(x) else None
    )

    return merged


# -- TABS ------------------------------------------------------------------

tab_activity, tab_deals = st.tabs(["Rep Activity", "Deal Health Monitor"])


# ═══════════════════════════════════════════════════════════════════════════
# TAB 1: REP ACTIVITY
# ═══════════════════════════════════════════════════════════════════════════

with tab_activity:
    st.header("Rep Activity Scoreboard")
    st.caption(f"{start_date.strftime('%b %d, %Y')} — {end_date.strftime('%b %d, %Y')}")

    # Date-filter raw activity data
    filt_meetings = _fdate_raw(_frep(data.meetings), "meeting_start_time")
    filt_calls = _fdate_raw(_frep(data.calls), "activity_date")
    filt_tasks = _fdate_raw(_frep(data.tasks), "completed_at")

    # KPI cards
    col1, col2, col3, col4 = st.columns(4)
    total = len(filt_meetings) + len(filt_calls) + len(filt_tasks)
    col1.metric("Total Activities", f"{total:,}")
    col2.metric("Meetings", f"{len(filt_meetings):,}")
    col3.metric("Calls", f"{len(filt_calls):,}")
    col4.metric("Tasks", f"{len(filt_tasks):,}")

    st.divider()

    # Leaderboard
    st.subheader("Activity Leaderboard")
    leaderboard = _compute_leaderboard(filt_meetings, filt_calls, filt_tasks)
    if not leaderboard.empty:
        st.dataframe(leaderboard, width="stretch", hide_index=True)

    st.divider()

    # By Rep chart
    if not leaderboard.empty:
        st.subheader("Activity by Rep")
        fig_rep = px.bar(
            leaderboard.melt(id_vars="Rep", value_vars=["Meetings", "Calls", "Completed Tasks"],
                             var_name="Type", value_name="Count"),
            x="Rep", y="Count", color="Type", barmode="group",
            color_discrete_map={"Meetings": "#10b981", "Calls": "#3b82f6", "Completed Tasks": "#f59e0b"},
        )
        fig_rep.update_layout(legend_title_text="", xaxis_title="", yaxis_title="Count")
        st.plotly_chart(fig_rep, use_container_width=True)

    st.divider()

    # Daily trend
    st.subheader("Daily Activity Trend")
    daily = _fdate(_frep(data.activity_counts_daily), "period_day")
    if not daily.empty:
        mcols = [c for c in ("meetings", "calls", "completed_tasks") if c in daily.columns]
        if mcols and "period_day" in daily.columns:
            trend = daily.groupby("period_day", dropna=False)[mcols].sum().reset_index()
            trend["period_day"] = pd.to_datetime(trend["period_day"])
            fig_trend = px.line(
                trend.melt(id_vars="period_day", value_vars=mcols, var_name="Type", value_name="Count"),
                x="period_day", y="Count", color="Type",
                color_discrete_map={"meetings": "#10b981", "calls": "#3b82f6", "completed_tasks": "#f59e0b"},
            )
            fig_trend.update_layout(xaxis_title="", yaxis_title="Count", legend_title_text="")
            st.plotly_chart(fig_trend, use_container_width=True)
    else:
        st.info("No daily trend data.")

    # Debug panel
    if show_debug:
        st.divider()
        st.subheader("DEBUG: Data Diagnostics")
        st.markdown(f"**Raw data (after rep filter, before date):** Calls: {len(data.calls):,} | Meetings: {len(data.meetings):,} | Tasks: {len(data.tasks):,}")

        calls_rep = _frep(data.calls)
        debug_rows = []
        for rep in selected_reps:
            rc = calls_rep[calls_rep["hubspot_owner_name"] == rep] if not calls_rep.empty and "hubspot_owner_name" in calls_rep.columns else pd.DataFrame()
            total_r = len(rc)
            if not rc.empty and "activity_date" in rc.columns:
                dt = pd.to_datetime(rc["activity_date"], errors="coerce")
                in_range = int(((dt.dt.date >= start_date) & (dt.dt.date <= end_date)).sum())
            else:
                in_range = 0
            debug_rows.append({"Rep": rep, "Total Calls": total_r, "In Range": in_range})
        st.dataframe(pd.DataFrame(debug_rows), width="stretch", hide_index=True)

        if not data.calls.empty and "activity_date" in data.calls.columns:
            dt_all = pd.to_datetime(data.calls["activity_date"], errors="coerce")
            st.markdown(f"**Calls date range:** {dt_all.min()} to {dt_all.max()}")


# ═══════════════════════════════════════════════════════════════════════════
# TAB 2: DEAL HEALTH MONITOR
# ═══════════════════════════════════════════════════════════════════════════

with tab_deals:
    st.header("Deal Health Monitor")
    st.caption("Active deals joined to activity data by company name")

    # Build deal health from ALL activity (not date-filtered — we want full history for health)
    all_meetings = _frep(data.meetings)
    all_calls = _frep(data.calls)
    all_tasks = _frep(data.tasks)
    deals_filtered = _frep(_fpipe(data.deals))

    health_df = _build_deal_health(deals_filtered, all_meetings, all_calls, all_tasks)

    if health_df.empty:
        st.info("No active deals found for selected filters.")
    else:
        # KPI cards
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Active Deals", f"{len(health_df):,}")
        active_val = health_df["amount"].sum() if "amount" in health_df.columns else 0
        c2.metric("Pipeline Value", f"${active_val:,.0f}")
        n_active = len(health_df[health_df["health"] == "Active"])
        n_stale = len(health_df[health_df["health"] == "Stale"])
        n_inactive = len(health_df[health_df["health"].isin(["Inactive", "No Activity"])])
        c3.metric("Active (7d)", f"{n_active}", delta=None)
        c4.metric("Needs Attention", f"{n_stale + n_inactive}", delta=None)

        st.divider()

        # Health distribution
        st.subheader("Deal Health Distribution")
        health_counts = health_df["health"].value_counts().reset_index()
        health_counts.columns = ["Health", "Count"]
        color_map = {"Active": "#10b981", "Stale": "#f59e0b", "Inactive": "#ef4444", "No Activity": "#94a3b8"}
        fig_health = px.pie(health_counts, names="Health", values="Count",
                            color="Health", color_discrete_map=color_map, hole=0.4)
        fig_health.update_layout(legend_title_text="")
        st.plotly_chart(fig_health, use_container_width=True)

        st.divider()

        # Flagged deals: Best Case / Commit / Expect with no recent activity
        st.subheader("Flagged Deals — Forecast but No Recent Activity")
        flagged_cats = {"Best Case", "Commit", "Expect"}
        if "forecast_category" in health_df.columns:
            flagged = health_df[
                (health_df["forecast_category"].isin(flagged_cats)) &
                (health_df["health"].isin(["Stale", "Inactive", "No Activity"]))
            ]
        else:
            flagged = pd.DataFrame()

        if not flagged.empty:
            flag_cols = [c for c in (
                "hubspot_owner_name", "deal_name", "company_name", "pipeline",
                "deal_stage", "forecast_category", "amount", "close_date",
                "health", "days_since_activity", "activities_30d",
            ) if c in flagged.columns]
            st.dataframe(
                flagged[flag_cols].sort_values("days_since_activity", ascending=False),
                width="stretch", hide_index=True,
            )
        else:
            st.success("All forecasted deals have recent activity.")

        st.divider()

        # Per-rep deal breakdown
        st.subheader("Deals by Rep")
        for rep in selected_reps:
            rep_deals = health_df[health_df["hubspot_owner_name"] == rep] if "hubspot_owner_name" in health_df.columns else pd.DataFrame()
            if rep_deals.empty:
                continue

            n = len(rep_deals)
            val = rep_deals["amount"].sum() if "amount" in rep_deals.columns else 0
            n_ok = len(rep_deals[rep_deals["health"] == "Active"])
            n_warn = len(rep_deals[rep_deals["health"].isin(["Stale", "Inactive", "No Activity"])])

            with st.expander(f"{rep} — {n} deals | ${val:,.0f} | {n_ok} active | {n_warn} needs attention"):
                show_cols = [c for c in (
                    "deal_name", "company_name", "deal_stage", "forecast_category",
                    "amount", "close_date", "health", "days_since_activity",
                    "calls", "meetings", "tasks", "activities_30d",
                ) if c in rep_deals.columns]
                display = rep_deals[show_cols].sort_values(
                    "days_since_activity", ascending=False, na_position="first"
                )
                st.dataframe(display, width="stretch", hide_index=True)


# -- Footer ----------------------------------------------------------------

st.sidebar.divider()
st.sidebar.caption(
    f"Data: {len(data.deals)} deals | {len(data.calls)} calls | "
    f"{len(data.meetings)} meetings | {len(data.tasks)} tasks"
)
