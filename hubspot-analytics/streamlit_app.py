"""
HubSpot Sales Analytics Dashboard
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


# ── Theme CSS ───────────────────────────────────────────────────────────
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&display=swap');

    .stApp { background-color: #1a1d23; font-family: 'DM Sans', sans-serif; }

    /* Sidebar */
    section[data-testid="stSidebar"] { background-color: #1e2128; border-right: 1px solid #2d323b; }
    section[data-testid="stSidebar"] h3,
    section[data-testid="stSidebar"] p,
    section[data-testid="stSidebar"] span,
    section[data-testid="stSidebar"] label,
    section[data-testid="stSidebar"] .stMarkdown {
        color: #d0d7de !important;
    }
    section[data-testid="stSidebar"] .stCaption p { color: #8a919e !important; }

    /* Global text */
    .stApp, .stApp p, .stApp span, .stApp label, .stApp li,
    .stMarkdown, .stMarkdown p, .stMarkdown span { color: #d0d7de; }

    /* KPI cards */
    .kpi-row { display: flex; gap: 12px; margin: 16px 0; }
    .kpi-card {
        flex: 1;
        background: #22262e;
        border: 1px solid #2d323b;
        border-radius: 10px;
        padding: 18px 20px;
    }
    .kpi-label { color: #8a919e; font-size: 0.72rem; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 6px; font-weight: 500; }
    .kpi-value { font-size: 1.85rem; font-weight: 700; line-height: 1.2; color: #e6edf3; }
    .kpi-green { color: #4ade80; }
    .kpi-blue { color: #60a5fa; }
    .kpi-amber { color: #fbbf24; }
    .kpi-red { color: #f87171; }

    /* Section header */
    .sec-header {
        color: #e6edf3;
        font-size: 1.05rem;
        font-weight: 600;
        padding: 10px 0 8px;
        margin: 12px 0 8px;
        border-bottom: 1px solid #2d323b;
    }

    /* Filter labels */
    .stMultiSelect label, .stDateInput label, .stSelectbox label {
        color: #8a919e !important;
        font-size: 0.78rem !important;
        text-transform: uppercase !important;
        letter-spacing: 0.8px !important;
    }

    /* Expanders */
    .stExpander { border: 1px solid #2d323b; border-radius: 10px; }
    .stExpander summary,
    .stExpander summary span,
    .stExpander summary p,
    .stExpander [data-testid="stExpanderDetails"] p,
    details summary span { color: #d0d7de !important; }

    /* Tabs */
    .stTabs [data-baseweb="tab"] { color: #8a919e; }
    .stTabs [aria-selected="true"] { color: #60a5fa; }

    /* Tables */
    .stDataFrame { border-radius: 8px; overflow: hidden; }

    /* Dividers */
    hr { border-color: #2d323b; }

    .block-container { padding-top: 1rem; }
</style>
""", unsafe_allow_html=True)


# ── Plotly Theme ────────────────────────────────────────────────────────
def _apply_plotly_theme(fig):
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="#22262e",
        font=dict(color="#b0b8c4", family="DM Sans, sans-serif", size=12),
        xaxis=dict(gridcolor="#2d323b", zerolinecolor="#2d323b"),
        yaxis=dict(gridcolor="#2d323b", zerolinecolor="#2d323b"),
        margin=dict(l=40, r=20, t=36, b=40),
        legend=dict(bgcolor="rgba(0,0,0,0)", orientation="h", y=-0.15),
        showlegend=True,
    )
    return fig

COLORS = {
    "meetings": "#4ade80", "calls": "#60a5fa", "tasks": "#fbbf24",
    "completed_tasks": "#fbbf24", "overdue": "#f87171",
    "active": "#4ade80", "stale": "#fbbf24", "inactive": "#f87171", "no_activity": "#555d6b",
}


# ── Data Loading ────────────────────────────────────────────────────────
@st.cache_data(ttl=600, show_spinner="Loading data...")
def get_data() -> dict:
    d = load_all()
    return {f: getattr(d, f) for f in d.__dataclass_fields__}

try:
    _d = get_data()
    data = AnalyticsData(**_d)
except Exception as e:
    st.error(f"**Data load failed:** {e}")
    st.stop()


# ── Sidebar: Navigation ────────────────────────────────────────────────
st.sidebar.markdown("### Calyx Activity Hub")
st.sidebar.markdown("---")

if "page" not in st.session_state:
    st.session_state.page = "Rep Activity"

for p in ["Rep Activity", "Deal Health Monitor"]:
    if st.sidebar.button(p, key=f"nav_{p}", use_container_width=True,
                         type="primary" if st.session_state.page == p else "secondary"):
        st.session_state.page = p
        st.rerun()

st.sidebar.markdown("---")
st.sidebar.caption(
    f"{len(data.deals)} deals · {len(data.calls)} calls · "
    f"{len(data.meetings)} mtgs · {len(data.emails)} emails · {len(data.tasks)} tasks"
)


# ── Top Filter Bar ──────────────────────────────────────────────────────
with st.container():
    f1, f2 = st.columns([1, 3])
    with f1:
        _ds = date.today() - timedelta(days=7)
        date_range = st.date_input("DATE RANGE", value=(_ds, date.today()), max_value=date.today())
        start_date, end_date = (date_range if isinstance(date_range, tuple) and len(date_range) == 2
                                else (_ds, date.today()))
    with f2:
        selected_reps = st.multiselect("REPS", REPS_IN_SCOPE, default=REPS_IN_SCOPE)

    selected_pipelines = st.multiselect("PIPELINES", PIPELINES_IN_SCOPE, default=PIPELINES_IN_SCOPE)

st.markdown("---")


# ── Helpers ─────────────────────────────────────────────────────────────
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

def _safe_sort(df, col, ascending=False):
    try:
        return df.sort_values(col, ascending=ascending)
    except Exception:
        return df

def kpi_html(cards):
    """cards = list of (label, value, accent_class)"""
    html = '<div class="kpi-row">'
    for label, value, accent in cards:
        vc = f"kpi-value {accent}" if accent else "kpi-value"
        html += f'<div class="kpi-card"><div class="kpi-label">{label}</div><div class="{vc}">{value}</div></div>'
    html += '</div>'
    st.markdown(html, unsafe_allow_html=True)

def hubspot_deal_url(deal_id):
    if pd.isna(deal_id) or str(deal_id).strip() == "": return ""
    return f"https://app.hubspot.com/contacts/44704741/deal/{int(float(str(deal_id)))}"


# ════════════════════════════════════════════════════════════════════════
# PAGE: REP ACTIVITY
# ════════════════════════════════════════════════════════════════════════

if st.session_state.page == "Rep Activity":

    st.markdown(f'<div class="sec-header">Activity — {start_date.strftime("%b %d")} to {end_date.strftime("%b %d, %Y")}</div>', unsafe_allow_html=True)

    filt_meetings = _fdate_raw(_frep(data.meetings), "meeting_start_time")
    filt_calls = _fdate_raw(_frep(data.calls), "activity_date")
    filt_tasks = _fdate_raw(_frep(data.tasks), "completed_at")
    filt_emails = _fdate_raw(_frep(data.emails), "activity_date")
    total = len(filt_meetings) + len(filt_calls) + len(filt_tasks) + len(filt_emails)

    kpi_html([
        ("Total Activities", f"{total:,}", ""),
        ("Meetings", f"{len(filt_meetings):,}", "kpi-green"),
        ("Calls", f"{len(filt_calls):,}", "kpi-blue"),
        ("Emails", f"{len(filt_emails):,}", "kpi-amber"),
        ("Tasks", f"{len(filt_tasks):,}", "kpi-amber"),
    ])

    # ── Leaderboard ──
    st.markdown('<div class="sec-header">Leaderboard</div>', unsafe_allow_html=True)

    lb_rows = []
    for rep in selected_reps:
        m = len(filt_meetings[filt_meetings["hubspot_owner_name"] == rep]) if not filt_meetings.empty and "hubspot_owner_name" in filt_meetings.columns else 0
        c = len(filt_calls[filt_calls["hubspot_owner_name"] == rep]) if not filt_calls.empty and "hubspot_owner_name" in filt_calls.columns else 0
        e = len(filt_emails[filt_emails["hubspot_owner_name"] == rep]) if not filt_emails.empty and "hubspot_owner_name" in filt_emails.columns else 0
        comp, over = 0, 0
        if not filt_tasks.empty and "hubspot_owner_name" in filt_tasks.columns:
            rt = filt_tasks[filt_tasks["hubspot_owner_name"] == rep]
            if "task_status" in rt.columns and not rt.empty:
                u = rt["task_status"].astype(str).str.upper().str.strip()
                comp = int(u.isin({"COMPLETED", "COMPLETE", "DONE"}).sum())
                over = int(u.isin({"OVERDUE", "PAST_DUE", "DEFERRED"}).sum())
        score = m*WEIGHTS["meetings"] + c*WEIGHTS["calls"] + e*WEIGHTS["emails"] + comp*WEIGHTS["completed_tasks"] + over*WEIGHTS["overdue_tasks"]
        lb_rows.append({"Rep": rep, "Meetings": m, "Calls": c, "Emails": e, "Tasks": comp, "Overdue": over, "Score": score})

    leaderboard = pd.DataFrame(lb_rows).sort_values("Score", ascending=False).reset_index(drop=True)
    st.dataframe(leaderboard, use_container_width=True, hide_index=True)

    # ── Charts row ──
    ch1, ch2 = st.columns(2)

    with ch1:
        st.markdown('<div class="sec-header">By Rep</div>', unsafe_allow_html=True)
        if not leaderboard.empty:
            fig = px.bar(
                leaderboard.melt(id_vars="Rep", value_vars=["Meetings", "Calls", "Emails", "Tasks"],
                                 var_name="Type", value_name="Count"),
                x="Rep", y="Count", color="Type", barmode="group",
                color_discrete_map={"Meetings": COLORS["meetings"], "Calls": COLORS["calls"],
                                    "Emails": "#c084fc", "Tasks": COLORS["tasks"]},
            )
            fig.update_layout(xaxis_title="", yaxis_title="")
            _apply_plotly_theme(fig)
            st.plotly_chart(fig, use_container_width=True)

    with ch2:
        st.markdown('<div class="sec-header">Daily Trend</div>', unsafe_allow_html=True)
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
                fig2.update_layout(xaxis_title="", yaxis_title="")
                _apply_plotly_theme(fig2)
                st.plotly_chart(fig2, use_container_width=True)
        else:
            st.info("No daily data for this range.")

    # ── Rep Drilldowns ──
    st.markdown('<div class="sec-header">Rep Details</div>', unsafe_allow_html=True)

    for _, row in leaderboard.iterrows():
        rep = row["Rep"]
        with st.expander(f"**{rep}** — {row['Meetings']} meetings · {row['Calls']} calls · {row['Emails']} emails · {row['Tasks']} tasks · Score: {row['Score']}"):

            dtab_m, dtab_c, dtab_e, dtab_t = st.tabs(["Meetings", "Calls", "Emails", "Tasks"])

            with dtab_m:
                rm = filt_meetings[filt_meetings["hubspot_owner_name"] == rep] if not filt_meetings.empty and "hubspot_owner_name" in filt_meetings.columns else pd.DataFrame()
                if not rm.empty:
                    show = [c for c in ("meeting_start_time", "meeting_name", "company_name",
                                        "meeting_outcome", "call_and_meeting_type", "has_gong") if c in rm.columns]
                    st.dataframe(_safe_sort(rm[show].copy(), show[0]) if show else rm,
                                 use_container_width=True, hide_index=True)
                else:
                    st.caption("No meetings this period.")

            with dtab_c:
                rc = filt_calls[filt_calls["hubspot_owner_name"] == rep] if not filt_calls.empty and "hubspot_owner_name" in filt_calls.columns else pd.DataFrame()
                if not rc.empty:
                    show = [c for c in ("activity_date", "company_name", "call_outcome",
                                        "call_direction", "call_duration", "call_and_meeting_type") if c in rc.columns]
                    st.dataframe(_safe_sort(rc[show].copy(), show[0]) if show else rc,
                                 use_container_width=True, hide_index=True)
                else:
                    st.caption("No calls this period.")

            with dtab_e:
                re = filt_emails[filt_emails["hubspot_owner_name"] == rep] if not filt_emails.empty and "hubspot_owner_name" in filt_emails.columns else pd.DataFrame()
                if not re.empty:
                    show = [c for c in ("activity_date", "email_subject", "company_name",
                                        "email_direction", "email_send_status",
                                        "email_from_address", "email_to_address") if c in re.columns]
                    st.dataframe(_safe_sort(re[show].copy(), show[0]) if show else re,
                                 use_container_width=True, hide_index=True)
                else:
                    st.caption("No emails this period.")

            with dtab_t:
                rt = filt_tasks[filt_tasks["hubspot_owner_name"] == rep] if not filt_tasks.empty and "hubspot_owner_name" in filt_tasks.columns else pd.DataFrame()
                if not rt.empty:
                    show = [c for c in ("completed_at", "task_title", "company_name",
                                        "task_status", "priority", "task_type") if c in rt.columns]
                    st.dataframe(_safe_sort(rt[show].copy(), show[0]) if show else rt,
                                 use_container_width=True, hide_index=True)
                else:
                    st.caption("No tasks this period.")


# ════════════════════════════════════════════════════════════════════════
# PAGE: DEAL HEALTH MONITOR
# ════════════════════════════════════════════════════════════════════════

elif st.session_state.page == "Deal Health Monitor":

    st.markdown('<div class="sec-header">Deal Health Monitor — Active Pipeline</div>', unsafe_allow_html=True)

    deals_f = _frep(_fpipe(data.deals))
    active_deals = deals_f[~deals_f["is_terminal"]].copy() if "is_terminal" in deals_f.columns else deals_f.copy()

    all_meetings = _frep(data.meetings)
    all_calls = _frep(data.calls)
    all_tasks = _frep(data.tasks)
    all_emails = _frep(data.emails)

    if active_deals.empty:
        st.info("No active deals for selected filters.")
    else:
        # Activity summary by company
        act_frames = []
        for df, atype, dcol in [(all_calls, "Call", "activity_date"), (all_meetings, "Meeting", "meeting_start_time"), (all_tasks, "Task", "completed_at"), (all_emails, "Email", "activity_date")]:
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
                last_activity=("_dt", "max"), total=("_dt", "count"),
                act_7d=("_dt", lambda x: (x >= day7).sum()),
                act_30d=("_dt", lambda x: (x >= day30).sum()),
                calls=("_type", lambda x: (x == "Call").sum()),
                mtgs=("_type", lambda x: (x == "Meeting").sum()),
                emails_ct=("_type", lambda x: (x == "Email").sum()),
                tasks_ct=("_type", lambda x: (x == "Task").sum()),
            ).reset_index()
        else:
            co_summary = pd.DataFrame(columns=["_co", "last_activity", "total", "act_7d", "act_30d", "calls", "mtgs", "emails_ct", "tasks_ct"])

        active_deals["_co"] = active_deals["company_name"].astype(str).str.strip().str.lower() if "company_name" in active_deals.columns else ""
        merged = active_deals.merge(co_summary, on="_co", how="left")

        for c in ["total", "act_7d", "act_30d", "calls", "mtgs", "emails_ct", "tasks_ct"]:
            if c in merged.columns: merged[c] = merged[c].fillna(0).astype(int)

        merged["health"] = merged.get("last_activity", pd.Series(dtype="datetime64[ns]")).apply(
            lambda x: "Active" if pd.notna(x) and x >= day7 else ("Stale" if pd.notna(x) and x >= day30 else ("Inactive" if pd.notna(x) else "No Activity"))
        )
        merged["days_since"] = merged.get("last_activity", pd.Series(dtype="datetime64[ns]")).apply(
            lambda x: (now - x).days if pd.notna(x) else None
        )

        # KPIs
        n_active = len(merged[merged["health"] == "Active"])
        n_warn = len(merged[merged["health"].isin(["Stale", "Inactive", "No Activity"])])
        kpi_html([
            ("Active Deals", f"{len(merged):,}", ""),
            ("Pipeline Value", f"${merged['amount'].sum():,.0f}" if "amount" in merged.columns else "$0", "kpi-blue"),
            ("Engaged (7d)", f"{n_active}", "kpi-green"),
            ("Needs Attention", f"{n_warn}", "kpi-red"),
        ])

        # Health chart + flagged deals
        h1, h2 = st.columns([1, 2])

        with h1:
            st.markdown('<div class="sec-header">Health Distribution</div>', unsafe_allow_html=True)
            hc = merged["health"].value_counts().reset_index()
            hc.columns = ["Health", "Count"]
            fig_h = px.pie(hc, names="Health", values="Count", color="Health", hole=0.45,
                           color_discrete_map={"Active": COLORS["active"], "Stale": COLORS["stale"],
                                               "Inactive": COLORS["inactive"], "No Activity": COLORS["no_activity"]})
            _apply_plotly_theme(fig_h)
            fig_h.update_traces(textinfo="label+value", textfont_color="#b0b8c4")
            st.plotly_chart(fig_h, use_container_width=True)

        with h2:
            st.markdown('<div class="sec-header">Flagged — Forecasted but No Recent Activity</div>', unsafe_allow_html=True)
            if "forecast_category" in merged.columns:
                flagged = merged[
                    (merged["forecast_category"].isin({"Best Case", "Commit", "Expect"})) &
                    (merged["health"].isin(["Stale", "Inactive", "No Activity"]))
                ]
            else:
                flagged = pd.DataFrame()

            if not flagged.empty:
                show = [c for c in ("hubspot_owner_name", "deal_name", "company_name", "deal_stage",
                                    "forecast_category", "amount", "close_date", "health", "days_since", "act_30d") if c in flagged.columns]
                st.dataframe(_safe_sort(flagged[show], "days_since"), use_container_width=True, hide_index=True)
            else:
                st.success("All forecasted deals have recent activity.")

        # Per-rep deals
        st.markdown('<div class="sec-header">Deals by Rep</div>', unsafe_allow_html=True)

        for rep in selected_reps:
            rd = merged[merged["hubspot_owner_name"] == rep] if "hubspot_owner_name" in merged.columns else pd.DataFrame()
            if rd.empty: continue

            n = len(rd)
            val = rd["amount"].sum() if "amount" in rd.columns else 0
            n_ok = len(rd[rd["health"] == "Active"])
            n_bad = n - n_ok

            with st.expander(f"**{rep}** — {n} deals · ${val:,.0f} · {n_ok} active · {n_bad} attention"):
                show = [c for c in ("deal_name", "company_name", "deal_stage", "forecast_category",
                                    "amount", "close_date", "health", "days_since",
                                    "calls", "mtgs", "emails_ct", "tasks_ct", "act_30d") if c in rd.columns]
                display = _safe_sort(rd[show].copy(), "days_since")

                if "deal_id" in rd.columns:
                    display = display.copy()
                    display.insert(0, "HubSpot", rd["deal_id"].apply(
                        lambda x: hubspot_deal_url(x) if pd.notna(x) and str(x).strip() else ""
                    ))

                st.dataframe(display, use_container_width=True, hide_index=True,
                    column_config={
                        "HubSpot": st.column_config.LinkColumn("HS Link", display_text="Open"),
                        "amount": st.column_config.NumberColumn("Amount", format="$%,.0f"),
                        "days_since": st.column_config.NumberColumn("Days Idle"),
                        "calls": "Calls", "mtgs": "Meetings", "emails_ct": "Emails", "tasks_ct": "Tasks",
                        "act_30d": st.column_config.NumberColumn("30d Activity"),
                    })
