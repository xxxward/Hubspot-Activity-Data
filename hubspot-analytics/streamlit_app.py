"""
HubSpot Sales Analytics Dashboard — Dark theme, sidebar nav, top filters, drilldowns.
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import date, timedelta
from src.utils.logging import setup_logging
from src.parsing.filters import REPS_IN_SCOPE, PIPELINES_IN_SCOPE
from src.metrics.scoring import WEIGHTS
from main import load_all, AnalyticsData

setup_logging()

st.set_page_config(page_title="Calyx Activity Hub", page_icon="\U0001f4ca", layout="wide", initial_sidebar_state="expanded")


# ── Custom CSS ──────────────────────────────────────────────────────────
st.markdown("""
<style>
    /* Dark theme overrides */
    .stApp { background-color: #0f1117; }
    section[data-testid="stSidebar"] {
        background-color: #161b22;
        border-right: 1px solid #21262d;
    }
    section[data-testid="stSidebar"] .stMarkdown h1 { color: #58a6ff; font-size: 1.3rem; }
    section[data-testid="stSidebar"] .stMarkdown p,
    section[data-testid="stSidebar"] .stMarkdown span { color: #c9d1d9; }

    /* Navigation buttons in sidebar */
    .nav-btn {
        display: block;
        width: 100%;
        padding: 12px 16px;
        margin: 4px 0;
        background: transparent;
        color: #c9d1d9;
        border: 1px solid transparent;
        border-radius: 8px;
        text-align: left;
        font-size: 0.95rem;
        cursor: pointer;
        transition: all 0.2s;
    }
    .nav-btn:hover { background: #21262d; border-color: #30363d; }
    .nav-btn.active { background: #1f6feb22; border-color: #1f6feb; color: #58a6ff; }

    /* KPI cards */
    .kpi-card {
        background: linear-gradient(135deg, #161b22, #1c2333);
        border: 1px solid #21262d;
        border-radius: 12px;
        padding: 20px 24px;
        text-align: center;
    }
    .kpi-label { color: #8b949e; font-size: 0.78rem; text-transform: uppercase; letter-spacing: 1.2px; margin-bottom: 4px; }
    .kpi-value { color: #e6edf3; font-size: 2rem; font-weight: 700; line-height: 1.2; }
    .kpi-accent { color: #3fb950; }
    .kpi-blue { color: #58a6ff; }
    .kpi-amber { color: #d29922; }
    .kpi-red { color: #f85149; }

    /* Section headers */
    .section-header {
        color: #e6edf3;
        font-size: 1.15rem;
        font-weight: 600;
        padding: 8px 0;
        margin: 8px 0;
        border-bottom: 1px solid #21262d;
    }

    /* Health badges */
    .health-active { background: #23803014; color: #3fb950; padding: 3px 10px; border-radius: 12px; font-size: 0.8rem; font-weight: 600; }
    .health-stale { background: #d2992214; color: #d29922; padding: 3px 10px; border-radius: 12px; font-size: 0.8rem; font-weight: 600; }
    .health-inactive { background: #f8514914; color: #f85149; padding: 3px 10px; border-radius: 12px; font-size: 0.8rem; font-weight: 600; }
    .health-none { background: #8b949e14; color: #8b949e; padding: 3px 10px; border-radius: 12px; font-size: 0.8rem; font-weight: 600; }

    /* Hide default streamlit padding */
    .block-container { padding-top: 1rem; }

    /* Plotly chart backgrounds */
    .stPlotlyChart { border-radius: 12px; overflow: hidden; }

    /* Data table styling */
    .stDataFrame { border-radius: 8px; overflow: hidden; }
</style>
""", unsafe_allow_html=True)


# ── Plotly theme ────────────────────────────────────────────────────────
PLOTLY_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="#161b22",
    font=dict(color="#c9d1d9", family="DM Sans, sans-serif"),
    xaxis=dict(gridcolor="#21262d", zerolinecolor="#21262d"),
    yaxis=dict(gridcolor="#21262d", zerolinecolor="#21262d"),
    margin=dict(l=40, r=20, t=40, b=40),
    legend=dict(bgcolor="rgba(0,0,0,0)"),
)

COLORS = {
    "meetings": "#3fb950",
    "calls": "#58a6ff",
    "tasks": "#d29922",
    "completed_tasks": "#d29922",
    "overdue": "#f85149",
    "active": "#3fb950",
    "stale": "#d29922",
    "inactive": "#f85149",
    "no_activity": "#484f58",
}


# ── Data Loading ────────────────────────────────────────────────────────
@st.cache_data(ttl=600, show_spinner="Loading data from Google Sheets...")
def get_data() -> dict:
    d = load_all()
    return {f: getattr(d, f) for f in d.__dataclass_fields__}

try:
    _d = get_data()
    data = AnalyticsData(**_d)
except Exception as e:
    st.error(f"**Data load failed:** {e}")
    st.stop()


# ── Sidebar Navigation ──────────────────────────────────────────────────
st.sidebar.markdown("# Calyx Activity Hub")
st.sidebar.markdown("---")

if "page" not in st.session_state:
    st.session_state.page = "Rep Activity"

pages = ["Rep Activity", "Deal Health Monitor"]
for p in pages:
    if st.sidebar.button(p, key=f"nav_{p}", use_container_width=True,
                         type="primary" if st.session_state.page == p else "secondary"):
        st.session_state.page = p
        st.rerun()

st.sidebar.markdown("---")
st.sidebar.caption(
    f"{len(data.deals)} deals · {len(data.calls)} calls · "
    f"{len(data.meetings)} meetings · {len(data.tasks)} tasks"
)


# ── Top Filter Bar ──────────────────────────────────────────────────────
fcol1, fcol2, fcol3 = st.columns([2, 3, 3])
with fcol1:
    _default_start = date.today() - timedelta(days=7)
    date_range = st.date_input("Date Range", value=(_default_start, date.today()), max_value=date.today(), label_visibility="collapsed")
    start_date, end_date = (date_range if isinstance(date_range, tuple) and len(date_range) == 2
                            else (_default_start, date.today()))
with fcol2:
    selected_reps = st.multiselect("Reps", REPS_IN_SCOPE, default=REPS_IN_SCOPE, label_visibility="collapsed")
with fcol3:
    selected_pipelines = st.multiselect("Pipelines", PIPELINES_IN_SCOPE, default=PIPELINES_IN_SCOPE, label_visibility="collapsed")


# ── Filter Helpers ──────────────────────────────────────────────────────
def _frep(df):
    if df.empty or "hubspot_owner_name" not in df.columns: return df
    return df[df["hubspot_owner_name"].isin(selected_reps)].copy()

def _fpipe(df):
    if df.empty or "pipeline" not in df.columns: return df
    return df[df["pipeline"].isin(selected_pipelines)].copy()

def _fdate_raw(df, date_col="activity_date"):
    if df.empty: return df
    for col in (date_col, "activity_date", "meeting_start_time", "created_date"):
        if col in df.columns:
            dt = pd.to_datetime(df[col], errors="coerce")
            mask = dt.notna() & (dt.dt.date >= start_date) & (dt.dt.date <= end_date)
            return df[mask].copy()
    return df

def _fdate(df, col="period_day"):
    if df.empty or col not in df.columns: return df
    dt = pd.to_datetime(df[col], errors="coerce").dt.date
    return df[(dt >= start_date) & (dt <= end_date)].copy()


# ── KPI Card Helper ─────────────────────────────────────────────────────
def kpi_card(label, value, accent_class=""):
    val_class = f"kpi-value {accent_class}" if accent_class else "kpi-value"
    st.markdown(f"""
    <div class="kpi-card">
        <div class="kpi-label">{label}</div>
        <div class="{val_class}">{value}</div>
    </div>
    """, unsafe_allow_html=True)


# ── HubSpot URL helpers ─────────────────────────────────────────────────
def hubspot_deal_url(deal_id):
    if pd.isna(deal_id) or str(deal_id).strip() == "": return ""
    return f"https://app.hubspot.com/contacts/44704741/deal/{int(float(str(deal_id)))}"

def hubspot_company_url(company_id):
    if pd.isna(company_id) or str(company_id).strip() == "": return ""
    return f"https://app.hubspot.com/contacts/44704741/company/{int(float(str(company_id)))}"


# ════════════════════════════════════════════════════════════════════════
# PAGE: REP ACTIVITY
# ════════════════════════════════════════════════════════════════════════

if st.session_state.page == "Rep Activity":

    st.markdown(f'<div class="section-header">Rep Activity — {start_date.strftime("%b %d")} to {end_date.strftime("%b %d, %Y")}</div>', unsafe_allow_html=True)

    # Filter data
    filt_meetings = _fdate_raw(_frep(data.meetings), "meeting_start_time")
    filt_calls = _fdate_raw(_frep(data.calls), "activity_date")
    filt_tasks = _fdate_raw(_frep(data.tasks), "completed_at")
    total = len(filt_meetings) + len(filt_calls) + len(filt_tasks)

    # KPI row
    k1, k2, k3, k4 = st.columns(4)
    with k1: kpi_card("Total Activities", f"{total:,}")
    with k2: kpi_card("Meetings", f"{len(filt_meetings):,}", "kpi-accent")
    with k3: kpi_card("Calls", f"{len(filt_calls):,}", "kpi-blue")
    with k4: kpi_card("Tasks", f"{len(filt_tasks):,}", "kpi-amber")

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Leaderboard ──
    st.markdown('<div class="section-header">Activity Leaderboard</div>', unsafe_allow_html=True)

    lb_rows = []
    for rep in selected_reps:
        m = len(filt_meetings[filt_meetings["hubspot_owner_name"] == rep]) if not filt_meetings.empty and "hubspot_owner_name" in filt_meetings.columns else 0
        c = len(filt_calls[filt_calls["hubspot_owner_name"] == rep]) if not filt_calls.empty and "hubspot_owner_name" in filt_calls.columns else 0
        comp, over = 0, 0
        if not filt_tasks.empty and "hubspot_owner_name" in filt_tasks.columns:
            rt = filt_tasks[filt_tasks["hubspot_owner_name"] == rep]
            if "task_status" in rt.columns and not rt.empty:
                u = rt["task_status"].astype(str).str.upper().str.strip()
                comp = int(u.isin({"COMPLETED", "COMPLETE", "DONE"}).sum())
                over = int(u.isin({"OVERDUE", "PAST_DUE", "DEFERRED"}).sum())
        score = m*WEIGHTS["meetings"] + c*WEIGHTS["calls"] + comp*WEIGHTS["completed_tasks"] + over*WEIGHTS["overdue_tasks"]
        lb_rows.append({"Rep": rep, "Meetings": m, "Calls": c, "Completed Tasks": comp, "Overdue": over, "Score": score})

    leaderboard = pd.DataFrame(lb_rows).sort_values("Score", ascending=False).reset_index(drop=True)
    st.dataframe(leaderboard, use_container_width=True, hide_index=True)

    # ── By Rep chart ──
    st.markdown("<br>", unsafe_allow_html=True)
    chart_cols = st.columns(2)

    with chart_cols[0]:
        st.markdown('<div class="section-header">Activity by Rep</div>', unsafe_allow_html=True)
        if not leaderboard.empty:
            fig = px.bar(
                leaderboard.melt(id_vars="Rep", value_vars=["Meetings", "Calls", "Completed Tasks"],
                                 var_name="Type", value_name="Count"),
                x="Rep", y="Count", color="Type", barmode="group",
                color_discrete_map={"Meetings": COLORS["meetings"], "Calls": COLORS["calls"], "Completed Tasks": COLORS["tasks"]},
            )
            fig.update_layout(**{**PLOTLY_LAYOUT, "legend": dict(bgcolor="rgba(0,0,0,0)", orientation="h", y=-0.15)}, showlegend=True)
            fig.update_layout(xaxis_title="", yaxis_title="")
            st.plotly_chart(fig, use_container_width=True)

    with chart_cols[1]:
        st.markdown('<div class="section-header">Daily Trend</div>', unsafe_allow_html=True)
        daily = _fdate(_frep(data.activity_counts_daily), "period_day")
        if not daily.empty:
            mcols = [c for c in ("meetings", "calls", "completed_tasks") if c in daily.columns]
            if mcols and "period_day" in daily.columns:
                trend = daily.groupby("period_day", dropna=False)[mcols].sum().reset_index()
                trend["period_day"] = pd.to_datetime(trend["period_day"])
                fig2 = px.line(
                    trend.melt(id_vars="period_day", value_vars=mcols, var_name="Type", value_name="Count"),
                    x="period_day", y="Count", color="Type",
                    color_discrete_map={"meetings": COLORS["meetings"], "calls": COLORS["calls"], "completed_tasks": COLORS["tasks"]},
                )
                fig2.update_traces(line_width=2.5)
                fig2.update_layout(**{**PLOTLY_LAYOUT, "legend": dict(bgcolor="rgba(0,0,0,0)", orientation="h", y=-0.15)}, showlegend=True)
                fig2.update_layout(xaxis_title="", yaxis_title="")
                st.plotly_chart(fig2, use_container_width=True)
        else:
            st.info("No daily data.")

    # ── Rep Drilldowns ──
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown('<div class="section-header">Rep Drilldowns</div>', unsafe_allow_html=True)

    for _, row in leaderboard.iterrows():
        rep = row["Rep"]
        with st.expander(f"**{rep}** — {row['Meetings']} meetings · {row['Calls']} calls · {row['Completed Tasks']} tasks · Score: {row['Score']}"):

            drill_tab_m, drill_tab_c, drill_tab_t = st.tabs(["Meetings", "Calls", "Tasks"])

            with drill_tab_m:
                rep_mtg = filt_meetings[filt_meetings["hubspot_owner_name"] == rep] if not filt_meetings.empty and "hubspot_owner_name" in filt_meetings.columns else pd.DataFrame()
                if not rep_mtg.empty:
                    show = [c for c in ("meeting_start_time", "meeting_name", "company_name",
                                        "meeting_outcome", "call_and_meeting_type", "has_gong") if c in rep_mtg.columns]
                    st.dataframe(rep_mtg[show].sort_values(show[0], ascending=False) if show else rep_mtg,
                                 use_container_width=True, hide_index=True)
                else:
                    st.info("No meetings in this period.")

            with drill_tab_c:
                rep_calls = filt_calls[filt_calls["hubspot_owner_name"] == rep] if not filt_calls.empty and "hubspot_owner_name" in filt_calls.columns else pd.DataFrame()
                if not rep_calls.empty:
                    show = [c for c in ("activity_date", "company_name", "call_outcome",
                                        "call_direction", "call_duration", "call_and_meeting_type") if c in rep_calls.columns]
                    st.dataframe(rep_calls[show].sort_values(show[0], ascending=False) if show else rep_calls,
                                 use_container_width=True, hide_index=True)
                else:
                    st.info("No calls in this period.")

            with drill_tab_t:
                rep_tasks = filt_tasks[filt_tasks["hubspot_owner_name"] == rep] if not filt_tasks.empty and "hubspot_owner_name" in filt_tasks.columns else pd.DataFrame()
                if not rep_tasks.empty:
                    show = [c for c in ("completed_at", "task_title", "company_name",
                                        "task_status", "priority", "task_type") if c in rep_tasks.columns]
                    st.dataframe(rep_tasks[show].sort_values(show[0], ascending=False) if show else rep_tasks,
                                 use_container_width=True, hide_index=True)
                else:
                    st.info("No tasks in this period.")


# ════════════════════════════════════════════════════════════════════════
# PAGE: DEAL HEALTH MONITOR
# ════════════════════════════════════════════════════════════════════════

elif st.session_state.page == "Deal Health Monitor":

    st.markdown('<div class="section-header">Deal Health Monitor — Active Pipeline</div>', unsafe_allow_html=True)

    # Get active deals
    deals_f = _frep(_fpipe(data.deals))
    active_deals = deals_f[~deals_f["is_terminal"]].copy() if "is_terminal" in deals_f.columns else deals_f.copy()

    # All activity (not date-filtered — full history for health assessment)
    all_meetings = _frep(data.meetings)
    all_calls = _frep(data.calls)
    all_tasks = _frep(data.tasks)

    if active_deals.empty:
        st.info("No active deals for selected filters.")
    else:
        # Build activity summary by company
        act_frames = []
        for df, atype, dcol in [(all_calls, "Call", "activity_date"), (all_meetings, "Meeting", "meeting_start_time"), (all_tasks, "Task", "completed_at")]:
            if df.empty or "company_name" not in df.columns: continue
            tmp = df[["company_name"]].copy()
            tmp["_dt"] = pd.to_datetime(df[dcol], errors="coerce") if dcol in df.columns else pd.NaT
            tmp["_type"] = atype
            act_frames.append(tmp)

        now = pd.Timestamp.now()
        day7, day30 = now - pd.Timedelta(days=7), now - pd.Timedelta(days=30)

        if act_frames:
            all_act = pd.concat(act_frames, ignore_index=True).dropna(subset=["company_name"])
            all_act["_co"] = all_act["company_name"].astype(str).str.strip().str.lower()

            co_summary = all_act.groupby("_co").agg(
                last_activity=("_dt", "max"),
                total=("_dt", "count"),
                act_7d=("_dt", lambda x: (x >= day7).sum()),
                act_30d=("_dt", lambda x: (x >= day30).sum()),
                calls=("_type", lambda x: (x == "Call").sum()),
                meetings_count=("_type", lambda x: (x == "Meeting").sum()),
                tasks_count=("_type", lambda x: (x == "Task").sum()),
            ).reset_index()
        else:
            co_summary = pd.DataFrame(columns=["_co", "last_activity", "total", "act_7d", "act_30d", "calls", "meetings_count", "tasks_count"])

        active_deals["_co"] = active_deals["company_name"].astype(str).str.strip().str.lower() if "company_name" in active_deals.columns else ""
        merged = active_deals.merge(co_summary, on="_co", how="left")

        for c in ["last_activity", "total", "act_7d", "act_30d", "calls", "meetings_count", "tasks_count"]:
            if c in merged.columns:
                if c == "last_activity":
                    pass
                else:
                    merged[c] = merged[c].fillna(0).astype(int)

        merged["health"] = merged["last_activity"].apply(
            lambda x: "Active" if pd.notna(x) and x >= day7 else ("Stale" if pd.notna(x) and x >= day30 else ("Inactive" if pd.notna(x) else "No Activity"))
        )
        merged["days_since"] = merged["last_activity"].apply(lambda x: (now - x).days if pd.notna(x) else None)

        # Add HubSpot links
        if "deal_id" in merged.columns:
            merged["deal_link"] = merged["deal_id"].apply(hubspot_deal_url)

        # KPI row
        k1, k2, k3, k4 = st.columns(4)
        with k1: kpi_card("Active Deals", f"{len(merged):,}")
        with k2: kpi_card("Pipeline Value", f"${merged['amount'].sum():,.0f}" if "amount" in merged.columns else "$0")
        n_active = len(merged[merged["health"] == "Active"])
        n_warn = len(merged[merged["health"].isin(["Stale", "Inactive", "No Activity"])])
        with k3: kpi_card("Engaged (7d)", f"{n_active}", "kpi-accent")
        with k4: kpi_card("Needs Attention", f"{n_warn}", "kpi-red")

        st.markdown("<br>", unsafe_allow_html=True)

        # Health chart + flagged deals side by side
        hcol1, hcol2 = st.columns([1, 2])

        with hcol1:
            st.markdown('<div class="section-header">Health Distribution</div>', unsafe_allow_html=True)
            hc = merged["health"].value_counts().reset_index()
            hc.columns = ["Health", "Count"]
            fig_h = px.pie(hc, names="Health", values="Count", color="Health", hole=0.45,
                           color_discrete_map={"Active": COLORS["active"], "Stale": COLORS["stale"],
                                               "Inactive": COLORS["inactive"], "No Activity": COLORS["no_activity"]})
            fig_h.update_layout(**PLOTLY_LAYOUT)
            fig_h.update_traces(textinfo="label+value", textfont_color="#c9d1d9")
            st.plotly_chart(fig_h, use_container_width=True)

        with hcol2:
            st.markdown('<div class="section-header">Flagged — Forecasted but No Recent Activity</div>', unsafe_allow_html=True)
            flagged_cats = {"Best Case", "Commit", "Expect"}
            if "forecast_category" in merged.columns:
                flagged = merged[
                    (merged["forecast_category"].isin(flagged_cats)) &
                    (merged["health"].isin(["Stale", "Inactive", "No Activity"]))
                ]
            else:
                flagged = pd.DataFrame()

            if not flagged.empty:
                show = [c for c in ("hubspot_owner_name", "deal_name", "company_name", "deal_stage",
                                    "forecast_category", "amount", "close_date", "health",
                                    "days_since", "act_30d") if c in flagged.columns]
                st.dataframe(flagged[show].sort_values("days_since", ascending=False, na_position="first"),
                             use_container_width=True, hide_index=True)
            else:
                st.success("All forecasted deals have recent activity.")

        st.markdown("<br>", unsafe_allow_html=True)

        # Per-rep deal breakdown with drilldowns
        st.markdown('<div class="section-header">Deals by Rep</div>', unsafe_allow_html=True)

        for rep in selected_reps:
            rep_deals = merged[merged["hubspot_owner_name"] == rep] if "hubspot_owner_name" in merged.columns else pd.DataFrame()
            if rep_deals.empty:
                continue

            n = len(rep_deals)
            val = rep_deals["amount"].sum() if "amount" in rep_deals.columns else 0
            n_ok = len(rep_deals[rep_deals["health"] == "Active"])
            n_bad = len(rep_deals[rep_deals["health"].isin(["Stale", "Inactive", "No Activity"])])

            with st.expander(f"**{rep}** — {n} deals · ${val:,.0f} · {n_ok} active · {n_bad} needs attention"):
                show = [c for c in (
                    "deal_name", "company_name", "deal_stage", "forecast_category",
                    "amount", "close_date", "health", "days_since",
                    "calls", "meetings_count", "tasks_count", "act_30d",
                ) if c in rep_deals.columns]

                display = rep_deals[show].sort_values("days_since", ascending=False, na_position="first")

                # Add HubSpot deal links as clickable column
                if "deal_id" in rep_deals.columns:
                    display = display.copy()
                    display.insert(0, "HubSpot", rep_deals["deal_id"].apply(
                        lambda x: hubspot_deal_url(x) if pd.notna(x) and str(x).strip() else ""
                    ))

                st.dataframe(
                    display,
                    use_container_width=True, hide_index=True,
                    column_config={
                        "HubSpot": st.column_config.LinkColumn("HubSpot", display_text="Open"),
                        "amount": st.column_config.NumberColumn("Amount", format="$%,.0f"),
                        "days_since": st.column_config.NumberColumn("Days Since Activity"),
                        "calls": st.column_config.NumberColumn("Calls"),
                        "meetings_count": st.column_config.NumberColumn("Meetings"),
                        "tasks_count": st.column_config.NumberColumn("Tasks"),
                        "act_30d": st.column_config.NumberColumn("Activity 30d"),
                    }
                )
