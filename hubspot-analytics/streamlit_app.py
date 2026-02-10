"""
Streamlit dashboard for HubSpot Sales Analytics.

Three tabs:
  1. Rep Activity   - scores, counts, trends
  2. Pipeline       - active value, stage counts, win rate
  3. Terminal Deals - won/lost, NCR, sales orders, cycle length

Sidebar filters: date range, rep, pipeline.
"""

import streamlit as st
import pandas as pd
from datetime import date, timedelta

from src.utils.logging import setup_logging
from src.parsing.filters import REPS_IN_SCOPE, PIPELINES_IN_SCOPE
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


# -- Sidebar Filters ------------------------------------------------------

st.sidebar.title("Filters")

_default_start = date.today() - timedelta(days=90)
date_range = st.sidebar.date_input("Date Range", value=(_default_start, date.today()), max_value=date.today())
start_date, end_date = (date_range if isinstance(date_range, tuple) and len(date_range) == 2
                        else (_default_start, date.today()))

selected_reps = st.sidebar.multiselect("Sales Reps", REPS_IN_SCOPE, default=REPS_IN_SCOPE)
selected_pipelines = st.sidebar.multiselect("Pipelines", PIPELINES_IN_SCOPE, default=PIPELINES_IN_SCOPE)


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
    if df.empty or col not in df.columns:
        return df
    dt = pd.to_datetime(df[col], errors="coerce").dt.date
    return df.loc[(dt >= start_date) & (dt <= end_date)].copy()


# -- Tabs ------------------------------------------------------------------

tab_act, tab_pipe, tab_term = st.tabs(["Rep Activity", "Pipeline", "Terminal Deals"])

# -- Tab 1: Rep Activity ---------------------------------------------------

with tab_act:
    st.header("Rep Activity Dashboard")

    # Leaderboard
    st.subheader("Activity Score Leaderboard")
    scores = _frep(data.rep_activity_score)
    if not scores.empty:
        st.dataframe(scores, width="stretch", hide_index=True)
    else:
        st.info("No activity score data.")

    st.divider()

    # Granularity picker
    grain = st.radio("Granularity", ["Daily", "Weekly", "Monthly"], index=1, horizontal=True)
    _gmap = {
        "Daily": ("activity_counts_daily", "period_day"),
        "Weekly": ("activity_counts_weekly", "period_week"),
        "Monthly": ("activity_counts_monthly", "period_month"),
    }
    counts_key, pcol = _gmap[grain]
    counts = _fdate(_frep(getattr(data, counts_key, pd.DataFrame())), pcol)

    if not counts.empty:
        st.subheader(f"Activity Counts ({grain})")
        st.dataframe(counts, width="stretch", hide_index=True)

        st.subheader("Activity Trend")
        mcols = [c for c in ("meetings", "calls", "emails", "completed_tasks", "overdue_tasks") if c in counts.columns]
        if mcols and pcol in counts.columns:
            chart = counts.groupby(pcol, dropna=False)[mcols].sum().reset_index().set_index(pcol)
            st.bar_chart(chart)
    else:
        st.info("No activity data for selected filters.")

    st.divider()
    st.subheader("Activity Score Trend (Weekly)")
    trend = _frep(data.rep_activity_score_trend)
    if not trend.empty and "period_week" in trend.columns:
        pivot = trend.pivot_table(index="period_week", columns="hubspot_owner_name",
                                  values="activity_score", aggfunc="sum").fillna(0)
        st.line_chart(pivot)
    else:
        st.info("No trend data.")


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
            st.dataframe(dbs, width="stretch", hide_index=True)

    with col_w:
        st.subheader("Win Rate")
        wr = _frep(_fpipe(data.win_rate))
        if not wr.empty:
            # Format win_rate as percentage in a new column to avoid .style
            wr_display = wr.copy()
            if "win_rate" in wr_display.columns:
                wr_display["win_rate"] = (wr_display["win_rate"] * 100).round(1).astype(str) + "%"
            st.dataframe(wr_display, width="stretch", hide_index=True)

    st.divider()
    st.subheader("Avg Days in Stage")
    adis = data.avg_days_in_stage
    if not adis.empty:
        st.bar_chart(adis.set_index("deal_stage")["avg_days"])


# -- Tab 3: Terminal Deals --------------------------------------------------

with tab_term:
    st.header("Terminal Deal Dashboard")

    st.subheader("Closed Won vs Closed Lost by Rep")
    wvl = _frep(data.closed_won_vs_lost)
    if not wvl.empty:
        st.dataframe(wvl, width="stretch", hide_index=True)
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
