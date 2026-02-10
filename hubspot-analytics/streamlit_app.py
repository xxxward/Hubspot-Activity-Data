"""
Streamlit dashboard for HubSpot Sales Analytics.

Tabs:
  1. Rep Activity   - scores, counts, trends
  2. Pipeline       - active value, stage counts, win rate
  3. Terminal Deals - won/lost, NCR, sales orders, cycle length

Sidebar filters: date range, rep, pipeline.
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import date, timedelta

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
date_range = st.sidebar.date_input("Date Range", value=(_default_start, date.today()), max_value=date.today())
start_date, end_date = (date_range if isinstance(date_range, tuple) and len(date_range) == 2
                        else (_default_start, date.today()))

selected_reps = st.sidebar.multiselect("Sales Reps", REPS_IN_SCOPE, default=REPS_IN_SCOPE)
selected_pipelines = st.sidebar.multiselect("Pipelines", PIPELINES_IN_SCOPE, default=PIPELINES_IN_SCOPE)

# Debug toggle
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


def _fdate(df: pd.DataFrame, col: str = "period_day") -> pd.DataFrame:
    """Filter a period-bucketed DataFrame by the sidebar date range."""
    if df.empty or col not in df.columns:
        return df
    dt = pd.to_datetime(df[col], errors="coerce").dt.date
    return df.loc[(dt >= start_date) & (dt <= end_date)].copy()


def _fdate_raw(df: pd.DataFrame, date_col: str = "activity_date") -> pd.DataFrame:
    """Filter a raw activity DataFrame by date range. Tries several date columns."""
    if df.empty:
        return df
    for col in (date_col, "activity_date", "meeting_start_time", "created_date"):
        if col in df.columns:
            dt = pd.to_datetime(df[col], errors="coerce").dt.date
            mask = (dt >= start_date) & (dt <= end_date)
            return df.loc[mask].copy()
    return df


def _compute_leaderboard(meetings: pd.DataFrame, calls: pd.DataFrame,
                         tasks: pd.DataFrame) -> pd.DataFrame:
    """Compute activity leaderboard from date-filtered raw data."""
    rows = []
    for rep in selected_reps:
        m_count = len(meetings[meetings["hubspot_owner_name"] == rep]) if not meetings.empty and "hubspot_owner_name" in meetings.columns else 0
        c_count = len(calls[calls["hubspot_owner_name"] == rep]) if not calls.empty and "hubspot_owner_name" in calls.columns else 0

        # Tasks: completed vs overdue
        if not tasks.empty and "hubspot_owner_name" in tasks.columns:
            rep_tasks = tasks[tasks["hubspot_owner_name"] == rep]
            status_col = "task_status" if "task_status" in rep_tasks.columns else None
            if status_col:
                upper = rep_tasks[status_col].astype(str).str.upper().str.strip()
                comp = int(upper.isin({"COMPLETED", "COMPLETE", "DONE"}).sum())
                overdue = int(upper.isin({"OVERDUE", "PAST_DUE", "DEFERRED"}).sum())
                # Also check past due_date
                if "due_date" in rep_tasks.columns:
                    past_due = pd.to_datetime(rep_tasks["due_date"], errors="coerce") < pd.Timestamp.now()
                    not_done = ~upper.isin({"COMPLETED", "COMPLETE", "DONE"})
                    overdue = max(overdue, int((past_due & not_done).sum()))
            else:
                comp = len(rep_tasks)
                overdue = 0
        else:
            comp = 0
            overdue = 0

        score = (m_count * WEIGHTS["meetings"] + c_count * WEIGHTS["calls"] +
                 comp * WEIGHTS["completed_tasks"] + overdue * WEIGHTS["overdue_tasks"])

        rows.append({
            "Rep": rep,
            "Meetings": m_count,
            "Calls": c_count,
            "Completed Tasks": comp,
            "Overdue Tasks": overdue,
            "Activity Score": score,
        })

    df = pd.DataFrame(rows).sort_values("Activity Score", ascending=False).reset_index(drop=True)
    return df


# -- Tabs ------------------------------------------------------------------

tab_act, tab_pipe, tab_term = st.tabs(["Rep Activity", "Pipeline", "Terminal Deals"])

# -- Tab 1: Rep Activity ---------------------------------------------------

with tab_act:
    st.header("Rep Activity Dashboard")
    st.caption(f"Showing: {start_date.strftime('%b %d, %Y')} — {end_date.strftime('%b %d, %Y')}")

    # Date-filter raw activity data FIRST, then compute leaderboard
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

    # Leaderboard — computed from date-filtered data
    st.subheader("Activity Leaderboard")
    leaderboard = _compute_leaderboard(filt_meetings, filt_calls, filt_tasks)
    if not leaderboard.empty:
        st.dataframe(leaderboard, width="stretch", hide_index=True)
    else:
        st.info("No activity data for selected filters.")

    st.divider()

    # By Rep bar chart
    if not leaderboard.empty:
        st.subheader("Activity by Rep")
        fig = px.bar(
            leaderboard,
            x="Rep", y=["Meetings", "Calls", "Completed Tasks"],
            barmode="group",
            color_discrete_sequence=["#10b981", "#3b82f6", "#f59e0b"],
        )
        fig.update_layout(legend_title_text="", xaxis_title="", yaxis_title="Count")
        st.plotly_chart(fig, use_container_width=True)

    st.divider()

    # Daily trend
    st.subheader("Daily Activity Trend")
    daily = _fdate(_frep(data.activity_counts_daily), "period_day")
    if not daily.empty:
        mcols = [c for c in ("meetings", "calls", "completed_tasks") if c in daily.columns]
        if mcols and "period_day" in daily.columns:
            trend = daily.groupby("period_day", dropna=False)[mcols].sum().reset_index()
            trend["period_day"] = pd.to_datetime(trend["period_day"])
            fig2 = px.line(
                trend.melt(id_vars="period_day", value_vars=mcols, var_name="Type", value_name="Count"),
                x="period_day", y="Count", color="Type",
                color_discrete_map={"meetings": "#10b981", "calls": "#3b82f6", "completed_tasks": "#f59e0b"},
            )
            fig2.update_layout(xaxis_title="", yaxis_title="Count", legend_title_text="")
            st.plotly_chart(fig2, use_container_width=True)
    else:
        st.info("No daily trend data.")

    # DEBUG section
    try:
        _show_debug = show_debug
    except NameError:
        _show_debug = False
    if _show_debug:
        st.divider()
        st.subheader("DEBUG: Data Diagnostics")

        # Raw data sizes
        st.markdown(f"**Raw data loaded (after rep filter, before date filter):**")
        st.markdown(f"- Calls: {len(data.calls):,} rows | Meetings: {len(data.meetings):,} rows | Tasks: {len(data.tasks):,} rows")

        # Calls diagnostics
        st.markdown("---")
        st.markdown("**Calls — per-rep breakdown**")
        calls_rep = _frep(data.calls)
        debug_rows = []
        for rep in selected_reps:
            rep_calls = calls_rep[calls_rep["hubspot_owner_name"] == rep] if not calls_rep.empty and "hubspot_owner_name" in calls_rep.columns else pd.DataFrame()

            total_rep = len(rep_calls)
            if not rep_calls.empty and "activity_date" in rep_calls.columns:
                dt = pd.to_datetime(rep_calls["activity_date"], errors="coerce")
                has_act_date = int(dt.notna().sum())
                no_act_date = int(dt.isna().sum())
                in_range_act = int(((dt.dt.date >= start_date) & (dt.dt.date <= end_date)).sum())
            else:
                has_act_date = 0
                no_act_date = total_rep
                in_range_act = 0

            if not rep_calls.empty and "created_date" in rep_calls.columns:
                dt2 = pd.to_datetime(rep_calls["created_date"], errors="coerce")
                in_range_created = int(((dt2.dt.date >= start_date) & (dt2.dt.date <= end_date)).sum())
            else:
                in_range_created = 0

            debug_rows.append({
                "Rep": rep,
                "Total (all time)": total_rep,
                "Has activity_date": has_act_date,
                "Missing activity_date": no_act_date,
                "In range (activity_date)": in_range_act,
                "In range (created_date)": in_range_created,
            })
        st.dataframe(pd.DataFrame(debug_rows), width="stretch", hide_index=True)

        # Calls date range
        if not data.calls.empty and "activity_date" in data.calls.columns:
            dt_all = pd.to_datetime(data.calls["activity_date"], errors="coerce")
            st.markdown(f"**Calls activity_date range:** {dt_all.min()} to {dt_all.max()}")
            st.markdown(f"**Null activity_dates:** {dt_all.isna().sum():,} / {len(data.calls):,}")

        if not data.calls.empty and "created_date" in data.calls.columns:
            dt_cr = pd.to_datetime(data.calls["created_date"], errors="coerce")
            st.markdown(f"**Calls created_date range:** {dt_cr.min()} to {dt_cr.max()}")

        # Meetings diagnostics
        st.markdown("---")
        st.markdown("**Meetings — per-rep breakdown**")
        mtg_rep = _frep(data.meetings)
        mtg_debug = []
        for rep in selected_reps:
            rep_mtg = mtg_rep[mtg_rep["hubspot_owner_name"] == rep] if not mtg_rep.empty and "hubspot_owner_name" in mtg_rep.columns else pd.DataFrame()

            total_rep = len(rep_mtg)
            for dcol in ("meeting_start_time", "activity_date", "created_date"):
                if not rep_mtg.empty and dcol in rep_mtg.columns:
                    dt = pd.to_datetime(rep_mtg[dcol], errors="coerce")
                    in_range = int(((dt.dt.date >= start_date) & (dt.dt.date <= end_date)).sum())
                    break
            else:
                in_range = 0

            has_gong = 0
            if not rep_mtg.empty and "has_gong" in rep_mtg.columns:
                has_gong = int(rep_mtg["has_gong"].sum())

            mtg_debug.append({
                "Rep": rep,
                "Total (all time)": total_rep,
                "In date range": in_range,
                "Has Gong": has_gong,
            })
        st.dataframe(pd.DataFrame(mtg_debug), width="stretch", hide_index=True)

        # Sample of Owen's calls to check UID mapping
        st.markdown("---")
        st.markdown("**Sample: Owen Labombard's calls (first 5 in date range)**")
        owen_calls = filt_calls[filt_calls["hubspot_owner_name"] == "Owen Labombard"] if not filt_calls.empty and "hubspot_owner_name" in filt_calls.columns else pd.DataFrame()
        if not owen_calls.empty:
            show_cols = [c for c in ("activity_date", "created_date", "call_outcome", "call_direction",
                                     "call_duration", "call_and_meeting_type", "company_name",
                                     "hubspot_owner_name", "activity_assigned_to") if c in owen_calls.columns]
            st.dataframe(owen_calls[show_cols].head(5), width="stretch", hide_index=True)
        else:
            st.warning("No calls found for Owen in date range.")

        # Check call_and_meeting_type distribution
        st.markdown("---")
        st.markdown("**Call types distribution (in date range, all reps)**")
        if not filt_calls.empty and "call_and_meeting_type" in filt_calls.columns:
            type_counts = filt_calls["call_and_meeting_type"].value_counts().reset_index()
            type_counts.columns = ["Type", "Count"]
            st.dataframe(type_counts, width="stretch", hide_index=True)

        # Check call_direction distribution
        if not filt_calls.empty and "call_direction" in filt_calls.columns:
            dir_counts = filt_calls["call_direction"].value_counts().reset_index()
            dir_counts.columns = ["Direction", "Count"]
            st.dataframe(dir_counts, width="stretch", hide_index=True)


# -- Tab 2: Pipeline -------------------------------------------------------

with tab_pipe:
    st.header("Pipeline Dashboard")

    st.subheader("Active Pipeline Value")
    apv = _fpipe(data.active_pipeline_value)
    if not apv.empty:
        c1, c2, c3 = st.columns(3)
        c1.metric("Total Value", f"${apv['total_value'].sum():,.0f}")
        c2.metric("Deal Count", f"{apv['deal_count'].sum():,}")
        c3.metric("Avg Deal Size", f"${apv['avg_value'].mean():,.0f}")
        st.dataframe(apv, width="stretch", hide_index=True)
    else:
        st.info("No active pipeline data.")

    st.divider()

    st.subheader("Deals Closing This Quarter")
    ctq = _frep(_fpipe(data.deals_closing_this_quarter))
    if not ctq.empty:
        show = [c for c in ("deal_name", "hubspot_owner_name", "pipeline",
                             "deal_stage", "amount", "close_date") if c in ctq.columns]
        st.dataframe(ctq[show] if show else ctq, width="stretch", hide_index=True)
    else:
        st.info("No deals closing this quarter.")

    st.divider()

    col_s, col_w = st.columns(2)
    with col_s:
        st.subheader("Deals by Stage")
        dbs = data.deal_count_by_stage
        if not dbs.empty:
            fig_stage = px.bar(dbs, x="deal_stage", y="count", color_discrete_sequence=["#6366f1"])
            fig_stage.update_layout(xaxis_title="", yaxis_title="Deals")
            st.plotly_chart(fig_stage, use_container_width=True)

    with col_w:
        st.subheader("Win Rate")
        wr = _frep(_fpipe(data.win_rate))
        if not wr.empty:
            wr_display = wr.copy()
            if "win_rate" in wr_display.columns:
                wr_display["win_rate_pct"] = (wr_display["win_rate"] * 100).round(1)
                fig_wr = px.bar(wr_display, x="hubspot_owner_name", y="win_rate_pct",
                                color_discrete_sequence=["#10b981"])
                fig_wr.update_layout(xaxis_title="", yaxis_title="Win Rate %")
                st.plotly_chart(fig_wr, use_container_width=True)

    st.divider()
    st.subheader("Avg Days in Stage")
    adis = data.avg_days_in_stage
    if not adis.empty and "deal_stage" in adis.columns and "avg_days" in adis.columns:
        fig_days = px.bar(adis, x="deal_stage", y="avg_days", color_discrete_sequence=["#f59e0b"])
        fig_days.update_layout(xaxis_title="", yaxis_title="Avg Days")
        st.plotly_chart(fig_days, use_container_width=True)


# -- Tab 3: Terminal Deals --------------------------------------------------

with tab_term:
    st.header("Terminal Deal Dashboard")

    st.subheader("Closed Won vs Closed Lost by Rep")
    wvl = _frep(data.closed_won_vs_lost)
    if not wvl.empty:
        st.dataframe(wvl, width="stretch", hide_index=True)
        if "hubspot_owner_name" in wvl.columns:
            melt_cols = [c for c in ("closed_won", "closed_lost") if c in wvl.columns]
            if melt_cols:
                fig_wvl = px.bar(
                    wvl.melt(id_vars="hubspot_owner_name", value_vars=melt_cols,
                             var_name="Status", value_name="Count"),
                    x="hubspot_owner_name", y="Count", color="Status", barmode="group",
                    color_discrete_map={"closed_won": "#10b981", "closed_lost": "#ef4444"},
                )
                fig_wvl.update_layout(xaxis_title="", legend_title_text="")
                st.plotly_chart(fig_wvl, use_container_width=True)
    else:
        st.info("No terminal deal data.")

    st.divider()

    col_n, col_so = st.columns(2)
    with col_n:
        st.subheader("NCR by Pipeline")
        ncr = _fpipe(data.ncr_by_pipeline)
        if not ncr.empty:
            st.dataframe(ncr, width="stretch", hide_index=True)
        else:
            st.info("No NCR data.")

    with col_so:
        st.subheader("Sales Orders Created in NS")
        so = _frep(_fpipe(data.sales_order_created))
        if not so.empty:
            st.dataframe(so, width="stretch", hide_index=True)
        else:
            st.info("No data.")

    st.divider()

    st.subheader("Average Sales Cycle (Days)")
    cyc = _frep(_fpipe(data.avg_sales_cycle))
    if not cyc.empty:
        st.dataframe(cyc, width="stretch", hide_index=True)

    st.divider()

    with st.expander("View All Terminal Deals"):
        td = data.deals
        if "is_terminal" in td.columns:
            td = td.loc[td["is_terminal"]]
        td = _frep(_fpipe(td))
        if not td.empty:
            show = [c for c in ("deal_name", "hubspot_owner_name", "pipeline", "deal_stage",
                                "terminal_status", "amount", "close_date", "created_date")
                    if c in td.columns]
            st.dataframe(td[show] if show else td, width="stretch", hide_index=True)
        else:
            st.info("No terminal deals for selected filters.")


# -- Footer ----------------------------------------------------------------

st.sidebar.divider()
st.sidebar.caption(
    f"Data: {len(data.deals)} deals | {len(data.calls)} calls | "
    f"{len(data.meetings)} meetings | {len(data.tasks)} tasks | "
    f"{len(data.tickets)} tickets"
)
