"""
Calyx Activity Hub — HubSpot Sales Analytics
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

st.set_page_config(page_title="Calyx Activity Hub", page_icon="📊", layout="wide", initial_sidebar_state="expanded")

# ── Theme ───────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

/* Base */
:root {
    --bg-primary: #0d1117;
    --bg-card: #161b22;
    --bg-hover: #1c2129;
    --border: #30363d;
    --text-primary: #e6edf3;
    --text-secondary: #8b949e;
    --text-muted: #6e7681;
    --accent-green: #3fb950;
    --accent-blue: #58a6ff;
    --accent-purple: #bc8cff;
    --accent-amber: #d29922;
    --accent-red: #f85149;
}

.stApp {
    background: var(--bg-primary);
    font-family: 'Inter', -apple-system, sans-serif;
}

/* Sidebar */
section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0d1117 0%, #161b22 100%);
    border-right: 1px solid var(--border);
}
section[data-testid="stSidebar"] * { color: var(--text-primary) !important; }
section[data-testid="stSidebar"] .stCaption * { color: var(--text-muted) !important; }

/* Global text */
.stApp, .stApp p, .stApp span, .stApp label, .stApp li,
.stMarkdown, .stMarkdown p, .stMarkdown span,
.stExpander summary, .stExpander summary span,
.stExpander [data-testid="stExpanderDetails"] p,
details summary span { color: var(--text-primary) !important; }

/* ── KPI Cards ── */
.kpi-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
    gap: 14px;
    margin: 20px 0;
}
.kpi {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 20px;
    position: relative;
    overflow: hidden;
}
.kpi::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 3px;
    border-radius: 12px 12px 0 0;
}
.kpi.green::before { background: var(--accent-green); }
.kpi.blue::before { background: var(--accent-blue); }
.kpi.purple::before { background: var(--accent-purple); }
.kpi.amber::before { background: var(--accent-amber); }
.kpi.red::before { background: var(--accent-red); }
.kpi-label {
    font-size: 0.7rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 1.2px;
    color: var(--text-secondary);
    margin-bottom: 8px;
}
.kpi-val {
    font-size: 1.9rem;
    font-weight: 800;
    color: var(--text-primary);
    line-height: 1;
}
.kpi.green .kpi-val { color: var(--accent-green); }
.kpi.blue .kpi-val { color: var(--accent-blue); }
.kpi.purple .kpi-val { color: var(--accent-purple); }
.kpi.amber .kpi-val { color: var(--accent-amber); }
.kpi.red .kpi-val { color: var(--accent-red); }

/* ── Section titles ── */
.sec-title {
    font-size: 0.8rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 1.5px;
    color: var(--text-secondary);
    padding: 16px 0 10px;
    margin: 8px 0;
}

/* ── Brand ── */
.brand {
    font-size: 1.1rem;
    font-weight: 800;
    letter-spacing: -0.5px;
    color: var(--accent-blue);
    margin-bottom: 4px;
}
.brand-sub {
    font-size: 0.72rem;
    color: var(--text-muted);
    letter-spacing: 0.5px;
    text-transform: uppercase;
}

/* ── Nav buttons ── */
.nav-label {
    font-size: 0.7rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 1px;
    color: var(--text-muted);
    margin: 20px 0 8px;
}

/* ── Misc ── */
.stExpander { border: 1px solid var(--border); border-radius: 12px; overflow: hidden; }
.stTabs [data-baseweb="tab"] { color: var(--text-secondary); font-weight: 500; }
.stTabs [aria-selected="true"] { color: var(--accent-blue); }
hr { border-color: var(--border) !important; }
.block-container { padding-top: 0.8rem; }
.stDataFrame { border-radius: 10px; overflow: hidden; }

/* Fix multiselect overflow */
.stMultiSelect > div { max-height: none !important; }
div[data-baseweb="select"] > div { flex-wrap: wrap !important; }
</style>
""", unsafe_allow_html=True)


# ── Plotly theme helper ─────────────────────────────────────────────────
def styled_fig(fig, height=340):
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="#161b22",
        font=dict(color="#8b949e", family="Inter, sans-serif", size=11),
        xaxis=dict(gridcolor="#21262d", zerolinecolor="#21262d", tickfont=dict(size=10)),
        yaxis=dict(gridcolor="#21262d", zerolinecolor="#21262d", tickfont=dict(size=10)),
        margin=dict(l=40, r=16, t=32, b=48),
        legend=dict(bgcolor="rgba(0,0,0,0)", orientation="h", y=-0.18, font=dict(size=10)),
        showlegend=True,
        height=height,
        bargap=0.3,
    )
    return fig

C = {"meetings": "#3fb950", "calls": "#58a6ff", "emails": "#bc8cff",
     "tasks": "#d29922", "completed_tasks": "#d29922", "overdue": "#f85149",
     "active": "#3fb950", "stale": "#d29922", "inactive": "#f85149", "none": "#484f58"}


# ── Data ────────────────────────────────────────────────────────────────
@st.cache_data(ttl=600, show_spinner="Loading data...")
def get_data():
    d = load_all()
    return {f: getattr(d, f) for f in d.__dataclass_fields__}

try:
    data = AnalyticsData(**get_data())
except Exception as e:
    st.error(f"**Data load failed:** {e}")
    st.stop()


# ── Sidebar ─────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown('<div class="brand">Calyx Activity Hub</div>', unsafe_allow_html=True)
    st.markdown('<div class="brand-sub">HubSpot Analytics</div>', unsafe_allow_html=True)
    st.markdown("---")

    st.markdown('<div class="nav-label">Navigation</div>', unsafe_allow_html=True)
    if "page" not in st.session_state:
        st.session_state.page = "activity"
    for key, label, icon in [("activity", "Rep Activity", "📊"), ("deals", "Deal Health", "🏥")]:
        if st.button(f"{icon}  {label}", key=f"n_{key}", use_container_width=True,
                     type="primary" if st.session_state.page == key else "secondary"):
            st.session_state.page = key
            st.rerun()

    st.markdown("---")
    st.caption(
        f"{len(data.deals)} deals · {len(data.calls)} calls\n"
        f"{len(data.meetings)} mtgs · {len(data.emails)} emails\n"
        f"{len(data.tasks)} tasks · {len(data.notes)} notes"
    )


# ── Filters (top) ──────────────────────────────────────────────────────
_ds = date.today() - timedelta(days=7)
date_range = st.date_input("📅 Date Range", value=(_ds, date.today()), max_value=date.today())
start_date, end_date = (date_range if isinstance(date_range, tuple) and len(date_range) == 2 else (_ds, date.today()))

c1, c2 = st.columns(2)
with c1:
    selected_reps = st.multiselect("👤 Sales Reps", REPS_IN_SCOPE, default=REPS_IN_SCOPE)
with c2:
    selected_pipelines = st.multiselect("🔀 Pipelines", PIPELINES_IN_SCOPE, default=PIPELINES_IN_SCOPE)


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

def _safe_sort(df, col, asc=False):
    try: return df.sort_values(col, ascending=asc)
    except: return df

def _display_df(df):
    """Clean a DataFrame for st.dataframe — fix mixed types that break PyArrow."""
    df = df.copy()
    for col in df.columns:
        if df[col].dtype == object:
            # Check for mixed Timestamp/string
            has_ts = df[col].apply(lambda x: isinstance(x, pd.Timestamp)).any()
            if has_ts:
                df[col] = pd.to_datetime(df[col], errors="coerce").dt.strftime("%Y-%m-%d %H:%M").fillna("")
    return df

def kpi(cards):
    html = '<div class="kpi-grid">'
    for label, val, accent in cards:
        cls = f"kpi {accent}" if accent else "kpi"
        html += f'<div class="{cls}"><div class="kpi-label">{label}</div><div class="kpi-val">{val}</div></div>'
    html += '</div>'
    st.markdown(html, unsafe_allow_html=True)

def hs_deal_url(did):
    if pd.isna(did) or not str(did).strip(): return ""
    return f"https://app.hubspot.com/contacts/44704741/deal/{int(float(str(did)))}"


# ════════════════════════════════════════════════════════════════════════
# PAGE: REP ACTIVITY
# ════════════════════════════════════════════════════════════════════════
if st.session_state.page == "activity":

    st.markdown("---")

    fm = _fdate_raw(_frep(data.meetings), "meeting_start_time")
    fc = _fdate_raw(_frep(data.calls), "activity_date")
    fe = _fdate_raw(_frep(data.emails), "activity_date")
    fn = _fdate_raw(_frep(data.notes), "activity_date")
    fk = _fdate_raw(_frep(data.tickets), "created_date")

    # Tasks: filter by due_date so we capture overdue (incomplete) tasks too
    ft_all = _frep(data.tasks)
    if not ft_all.empty and "due_date" in ft_all.columns:
        due_dt = pd.to_datetime(ft_all["due_date"], errors="coerce")
        ft = ft_all[due_dt.notna() & (due_dt.dt.date >= start_date) & (due_dt.dt.date <= end_date)].copy()
    else:
        ft = _fdate_raw(ft_all, "completed_at")
    total = len(fm) + len(fc) + len(ft) + len(fe) + len(fn) + len(fk)

    kpi([
        ("Total", f"{total:,}", ""),
        ("Meetings", f"{len(fm):,}", "green"),
        ("Calls", f"{len(fc):,}", "blue"),
        ("Emails", f"{len(fe):,}", "purple"),
        ("Tasks", f"{len(ft):,}", "amber"),
        ("Notes", f"{len(fn):,}", ""),
        ("Tickets", f"{len(fk):,}", "red"),
    ])

    # Leaderboard
    st.markdown('<div class="sec-title">Leaderboard</div>', unsafe_allow_html=True)

    rows = []
    for rep in selected_reps:
        m = len(fm[fm["hubspot_owner_name"] == rep]) if not fm.empty and "hubspot_owner_name" in fm.columns else 0
        c = len(fc[fc["hubspot_owner_name"] == rep]) if not fc.empty and "hubspot_owner_name" in fc.columns else 0
        e = len(fe[fe["hubspot_owner_name"] == rep]) if not fe.empty and "hubspot_owner_name" in fe.columns else 0
        n = len(fn[fn["hubspot_owner_name"] == rep]) if not fn.empty and "hubspot_owner_name" in fn.columns else 0
        k = len(fk[fk["hubspot_owner_name"] == rep]) if not fk.empty and "hubspot_owner_name" in fk.columns else 0

        # Task completion & overdue
        comp, over = 0, 0
        if not ft.empty and "hubspot_owner_name" in ft.columns:
            rt = ft[ft["hubspot_owner_name"] == rep]
            if not rt.empty and "task_status" in rt.columns:
                status = rt["task_status"].astype(str).str.upper().str.strip()
                comp = int(status.isin({"COMPLETED", "COMPLETE", "DONE"}).sum())
                # Overdue = status is NOT completed AND due_date < today
                if "due_date" in rt.columns:
                    due = pd.to_datetime(rt["due_date"], errors="coerce")
                    not_done = ~status.isin({"COMPLETED", "COMPLETE", "DONE"})
                    past_due = due.notna() & (due.dt.date < date.today())
                    over = int((not_done & past_due).sum())

        score = m*WEIGHTS["meetings"] + c*WEIGHTS["calls"] + e*WEIGHTS["emails"] + comp*WEIGHTS["completed_tasks"] + over*WEIGHTS["overdue_tasks"]
        rows.append({"Rep": rep, "Meetings": m, "Calls": c, "Emails": e, "Tasks": comp,
                     "Overdue": over, "Notes": n, "Tickets": k, "Score": score})

    lb = pd.DataFrame(rows).sort_values("Score", ascending=False).reset_index(drop=True)
    st.dataframe(lb, use_container_width=True, hide_index=True)

    # Charts
    ch1, ch2 = st.columns(2)
    with ch1:
        st.markdown('<div class="sec-title">Activity by Rep</div>', unsafe_allow_html=True)
        if not lb.empty:
            fig = px.bar(
                lb.melt(id_vars="Rep", value_vars=["Meetings", "Calls", "Emails", "Tasks", "Notes", "Tickets"],
                        var_name="Type", value_name="Count"),
                x="Rep", y="Count", color="Type", barmode="group",
                color_discrete_map={"Meetings": C["meetings"], "Calls": C["calls"],
                                    "Emails": C["emails"], "Tasks": C["tasks"],
                                    "Notes": "#8b949e", "Tickets": C["inactive"]},
            )
            fig.update_layout(xaxis_title="", yaxis_title="")
            st.plotly_chart(styled_fig(fig), use_container_width=True)

    with ch2:
        st.markdown('<div class="sec-title">Daily Trend</div>', unsafe_allow_html=True)
        daily = _fdate(_frep(data.activity_counts_daily), "period_day")
        if not daily.empty:
            mcols = [c for c in ("meetings", "calls", "emails", "completed_tasks") if c in daily.columns]
            if mcols and "period_day" in daily.columns:
                trend = daily.groupby("period_day", dropna=False)[mcols].sum().reset_index()
                trend["period_day"] = pd.to_datetime(trend["period_day"])
                fig2 = px.line(
                    trend.melt(id_vars="period_day", value_vars=mcols, var_name="Type", value_name="Count"),
                    x="period_day", y="Count", color="Type",
                    color_discrete_map={"meetings": C["meetings"], "calls": C["calls"],
                                        "emails": C["emails"], "completed_tasks": C["tasks"]},
                )
                fig2.update_traces(line_width=2.5, mode="lines+markers")
                fig2.update_layout(xaxis_title="", yaxis_title="")
                st.plotly_chart(styled_fig(fig2), use_container_width=True)
        else:
            st.caption("No daily data for this range.")

    # Drilldowns
    st.markdown('<div class="sec-title">Rep Details</div>', unsafe_allow_html=True)

    for _, r in lb.iterrows():
        rep = r["Rep"]
        with st.expander(f"**{rep}**  ·  {r['Meetings']} mtgs  ·  {r['Calls']} calls  ·  {r['Emails']} emails  ·  {r['Tasks']} tasks  ·  {r['Notes']} notes  ·  {r['Tickets']} tickets  ·  Score {r['Score']}"):
            t1, t2, t3, t4, t5, t6 = st.tabs(["🟢 Meetings", "🔵 Calls", "🟣 Emails", "🟡 Tasks", "📝 Notes", "🎫 Tickets"])

            with t1:
                rm = fm[fm["hubspot_owner_name"] == rep] if not fm.empty and "hubspot_owner_name" in fm.columns else pd.DataFrame()
                if not rm.empty:
                    s = [c for c in ("meeting_start_time", "meeting_name", "company_name", "meeting_outcome", "call_and_meeting_type", "has_gong") if c in rm.columns]
                    st.dataframe(_display_df(_safe_sort(rm[s].copy(), s[0]) if s else rm), use_container_width=True, hide_index=True)
                else: st.caption("No meetings.")

            with t2:
                rc = fc[fc["hubspot_owner_name"] == rep] if not fc.empty and "hubspot_owner_name" in fc.columns else pd.DataFrame()
                if not rc.empty:
                    s = [c for c in ("activity_date", "company_name", "call_outcome", "call_direction", "call_duration", "call_and_meeting_type") if c in rc.columns]
                    st.dataframe(_display_df(_safe_sort(rc[s].copy(), s[0]) if s else rc), use_container_width=True, hide_index=True)
                else: st.caption("No calls.")

            with t3:
                re = fe[fe["hubspot_owner_name"] == rep] if not fe.empty and "hubspot_owner_name" in fe.columns else pd.DataFrame()
                if not re.empty:
                    s = [c for c in ("activity_date", "email_subject", "company_name", "email_direction", "email_send_status", "email_from_address", "email_to_address") if c in re.columns]
                    st.dataframe(_display_df(_safe_sort(re[s].copy(), s[0]) if s else re), use_container_width=True, hide_index=True)
                else: st.caption("No emails.")

            with t4:
                rt = ft[ft["hubspot_owner_name"] == rep] if not ft.empty and "hubspot_owner_name" in ft.columns else pd.DataFrame()
                if not rt.empty:
                    # Add overdue flag for display
                    rt_disp = rt.copy()
                    if "due_date" in rt_disp.columns and "task_status" in rt_disp.columns:
                        due = pd.to_datetime(rt_disp["due_date"], errors="coerce")
                        status = rt_disp["task_status"].astype(str).str.upper().str.strip()
                        not_done = ~status.isin({"COMPLETED", "COMPLETE", "DONE"})
                        past_due = due.notna() & (due.dt.date < date.today())
                        rt_disp["overdue"] = (not_done & past_due).map({True: "⚠️ Yes", False: ""})
                    s = [c for c in ("due_date", "task_title", "company_name", "task_status", "overdue", "priority", "task_type") if c in rt_disp.columns]
                    st.dataframe(_display_df(_safe_sort(rt_disp[s].copy(), s[0]) if s else rt_disp), use_container_width=True, hide_index=True)
                else: st.caption("No tasks.")

            with t5:
                rn = fn[fn["hubspot_owner_name"] == rep] if not fn.empty and "hubspot_owner_name" in fn.columns else pd.DataFrame()
                if not rn.empty:
                    s = [c for c in ("activity_date", "deal_name", "company_name", "note_body") if c in rn.columns]
                    st.dataframe(_display_df(_safe_sort(rn[s].copy(), s[0]) if s else rn), use_container_width=True, hide_index=True)
                else: st.caption("No notes.")

            with t6:
                rk = fk[fk["hubspot_owner_name"] == rep] if not fk.empty and "hubspot_owner_name" in fk.columns else pd.DataFrame()
                if not rk.empty:
                    s = [c for c in ("created_date", "ticket_name", "company_name", "ticket_status", "priority", "ticket_category") if c in rk.columns]
                    st.dataframe(_display_df(_safe_sort(rk[s].copy(), s[0]) if s else rk), use_container_width=True, hide_index=True)
                else: st.caption("No tickets.")


# ════════════════════════════════════════════════════════════════════════
# PAGE: DEAL HEALTH
# ════════════════════════════════════════════════════════════════════════
elif st.session_state.page == "deals":

    st.markdown("---")

    deals_f = _frep(_fpipe(data.deals))
    active = deals_f[~deals_f["is_terminal"]].copy() if "is_terminal" in deals_f.columns else deals_f.copy()

    # For deal health: use ALL activity (not rep-filtered) — any touch on the account matters
    all_meetings = data.meetings
    all_calls = data.calls
    all_tasks = data.tasks
    all_emails = data.emails
    all_notes = data.notes
    all_tickets = data.tickets

    # Rep-filtered notes for display
    an = _frep(data.notes)

    if active.empty:
        st.info("No active deals.")
    else:
        # ── Build per-deal activity by matching on BOTH company_name AND deal_name ──
        now = pd.Timestamp.now()
        d7, d30 = now - pd.Timedelta(days=7), now - pd.Timedelta(days=30)

        # Collect all activity with company + deal_name (where available)
        activity_sources = [
            (all_calls, "Call", "activity_date"),
            (all_meetings, "Meeting", "meeting_start_time"),
            (all_tasks, "Task", "due_date"),
            (all_emails, "Email", "activity_date"),
            (all_notes, "Note", "activity_date"),
            (all_tickets, "Ticket", "created_date"),
        ]

        frames = []
        for df, typ, dc in activity_sources:
            if df.empty: continue
            t = pd.DataFrame()
            t["company_name"] = df["company_name"].astype(str).str.strip() if "company_name" in df.columns else ""
            t["deal_name"] = df["deal_name"].astype(str).str.strip() if "deal_name" in df.columns else ""
            t["_dt"] = pd.to_datetime(df[dc], errors="coerce") if dc in df.columns else pd.NaT
            t["_tp"] = typ
            t["_is_rep"] = df["hubspot_owner_name"].isin(REPS_IN_SCOPE) if "hubspot_owner_name" in df.columns else False
            # Grab summary fields for AI analysis
            if typ == "Email" and "email_subject" in df.columns:
                t["_summary"] = df["email_subject"].astype(str)
            elif typ == "Note" and "note_body" in df.columns:
                t["_summary"] = df["note_body"].astype(str).str.replace(r'<[^>]+>', '', regex=True).str[:200]
            elif typ == "Meeting" and "meeting_name" in df.columns:
                t["_summary"] = df["meeting_name"].astype(str)
            elif typ == "Call" and "call_outcome" in df.columns:
                t["_summary"] = df["call_outcome"].astype(str)
            elif typ == "Task" and "task_title" in df.columns:
                t["_summary"] = df["task_title"].astype(str)
            elif typ == "Ticket" and "ticket_name" in df.columns:
                t["_summary"] = df["ticket_name"].astype(str)
            else:
                t["_summary"] = ""
            t["_owner"] = df["hubspot_owner_name"].astype(str) if "hubspot_owner_name" in df.columns else ""
            frames.append(t)

        if frames:
            all_act = pd.concat(frames, ignore_index=True)
            all_act["_co"] = all_act["company_name"].astype(str).str.strip().str.lower()
            all_act["_dn"] = all_act["deal_name"].astype(str).str.strip().str.lower()
        else:
            all_act = pd.DataFrame()

        # For each deal, find matching activity by:
        #   1. company_name match (primary)
        #   2. deal_name match (secondary — catches notes/tasks linked to deal)
        active["_co"] = active["company_name"].astype(str).str.strip().str.lower() if "company_name" in active.columns else ""
        active["_dn"] = active["deal_name"].astype(str).str.strip().str.lower() if "deal_name" in active.columns else ""

        deal_health_rows = []
        deal_activity_cache = {}  # cache for AI analysis

        for idx, deal in active.iterrows():
            co = deal["_co"]
            dn = deal["_dn"]

            if not all_act.empty:
                # Match by company OR deal_name
                mask_co = (all_act["_co"] == co) & (co != "")
                mask_dn = (all_act["_dn"] == dn) & (dn != "")
                matched_act = all_act[mask_co | mask_dn].copy()
            else:
                matched_act = pd.DataFrame()

            if not matched_act.empty:
                last_act = matched_act["_dt"].max()
                total = len(matched_act)
                a7 = int((matched_act["_dt"] >= d7).sum())
                a30 = int((matched_act["_dt"] >= d30).sum())
                calls = int((matched_act["_tp"] == "Call").sum())
                mtgs = int((matched_act["_tp"] == "Meeting").sum())
                emails = int((matched_act["_tp"] == "Email").sum())
                tasks = int((matched_act["_tp"] == "Task").sum())
                notes = int((matched_act["_tp"] == "Note").sum())
                tickets = int((matched_act["_tp"] == "Ticket").sum())
                rep_act = int(matched_act["_is_rep"].sum())
                other_act = total - rep_act
            else:
                last_act = pd.NaT
                total = a7 = a30 = calls = mtgs = emails = tasks = notes = tickets = rep_act = other_act = 0

            health = "Active" if pd.notna(last_act) and last_act >= d7 else \
                     "Stale" if pd.notna(last_act) and last_act >= d30 else \
                     "Inactive" if pd.notna(last_act) else "No Activity"
            days_idle = (now - last_act).days if pd.notna(last_act) else None

            row = deal.to_dict()
            row.update({
                "last_act": last_act, "total": total, "a7": a7, "a30": a30,
                "calls": calls, "mtgs": mtgs, "emails": emails, "tasks": tasks,
                "notes": notes, "tickets": tickets,
                "rep_activity": rep_act, "other_activity": other_act,
                "health": health, "days_idle": days_idle,
            })
            deal_health_rows.append(row)

            # Cache recent activity for AI analysis (last 30d, max 15 items)
            if not matched_act.empty:
                recent = matched_act[matched_act["_dt"] >= d30].sort_values("_dt", ascending=False).head(15)
                deal_activity_cache[dn] = recent

        mg = pd.DataFrame(deal_health_rows)

        # KPIs
        na = len(mg[mg["health"] == "Active"])
        nw = len(mg) - na
        matched_deals = mg[mg["total"] > 0]
        kpi([
            ("Active Deals", f"{len(mg):,}", ""),
            ("Pipeline", f"${mg['amount'].sum():,.0f}" if "amount" in mg.columns else "$0", "blue"),
            ("Engaged 7d", f"{na}", "green"),
            ("Needs Attention", f"{nw}", "red"),
            ("Company Match", f"{len(matched_deals)}/{len(mg)}", ""),
        ])

        # Health + Flagged
        h1, h2 = st.columns([1, 2])
        with h1:
            st.markdown('<div class="sec-title">Health</div>', unsafe_allow_html=True)
            hc = mg["health"].value_counts().reset_index()
            hc.columns = ["Health", "Count"]
            fh = px.pie(hc, names="Health", values="Count", color="Health", hole=0.5,
                        color_discrete_map={"Active": C["active"], "Stale": C["stale"],
                                            "Inactive": C["inactive"], "No Activity": C["none"]})
            styled_fig(fh, 300)
            fh.update_traces(textinfo="label+value", textfont=dict(color="#e6edf3", size=11))
            st.plotly_chart(fh, use_container_width=True)

        with h2:
            st.markdown('<div class="sec-title">Flagged — Forecast with No Recent Activity</div>', unsafe_allow_html=True)
            if "forecast_category" in mg.columns:
                fl = mg[(mg["forecast_category"].isin({"Best Case", "Commit", "Expect"})) &
                        (mg["health"].isin(["Stale", "Inactive", "No Activity"]))]
            else: fl = pd.DataFrame()
            if not fl.empty:
                sc = [c for c in ("hubspot_owner_name", "deal_name", "company_name", "deal_stage",
                                  "forecast_category", "amount", "close_date", "health", "days_idle", "a30") if c in fl.columns]
                st.dataframe(_safe_sort(fl[sc], "days_idle"), use_container_width=True, hide_index=True)
            else:
                st.success("✅ All forecasted deals have recent activity.")

        # Per-rep deals
        st.markdown('<div class="sec-title">Deals by Rep</div>', unsafe_allow_html=True)
        for rep in selected_reps:
            rd = mg[mg["hubspot_owner_name"] == rep] if "hubspot_owner_name" in mg.columns else pd.DataFrame()
            if rd.empty: continue
            n_deals = len(rd)
            v = rd["amount"].sum() if "amount" in rd.columns else 0
            nok = len(rd[rd["health"] == "Active"])

            with st.expander(f"**{rep}**  ·  {n_deals} deals  ·  ${v:,.0f}  ·  {nok} active  ·  {n_deals - nok} attention"):
                sc = [c for c in ("deal_name", "company_name", "deal_stage", "forecast_category",
                                  "amount", "close_date", "health", "days_idle",
                                  "rep_activity", "other_activity",
                                  "calls", "mtgs", "emails", "notes", "tickets", "tasks", "a30") if c in rd.columns]
                disp = _safe_sort(rd[sc].copy(), "days_idle")
                if "deal_id" in rd.columns:
                    disp = disp.copy()
                    disp.insert(0, "HS", rd["deal_id"].apply(lambda x: hs_deal_url(x) if pd.notna(x) and str(x).strip() else ""))
                st.dataframe(disp, use_container_width=True, hide_index=True,
                    column_config={
                        "HS": st.column_config.LinkColumn("Link", display_text="Open"),
                        "amount": st.column_config.NumberColumn("Amount", format="$%,.0f"),
                        "days_idle": st.column_config.NumberColumn("Days Idle"),
                        "calls": "Calls", "mtgs": "Mtgs", "emails": "Emails",
                        "notes": "Notes", "tickets": "Tickets", "tasks": "Tasks",
                        "rep_activity": st.column_config.NumberColumn("Rep"),
                        "other_activity": st.column_config.NumberColumn("Other"),
                        "a30": st.column_config.NumberColumn("30d"),
                    })

                # Per-deal activity timeline + AI analysis
                for _, deal_row in rd.iterrows():
                    dn_key = str(deal_row.get("deal_name", "")).strip().lower()
                    cached = deal_activity_cache.get(dn_key)
                    if cached is not None and not cached.empty:
                        with st.expander(f"📋 {deal_row.get('deal_name', 'Unknown')} — Activity Timeline"):
                            # Show activity timeline
                            timeline = cached[["_dt", "_tp", "_owner", "_summary"]].copy()
                            timeline.columns = ["Date", "Type", "By", "Summary"]
                            timeline["Date"] = pd.to_datetime(timeline["Date"], errors="coerce").dt.strftime("%Y-%m-%d")
                            timeline["Summary"] = timeline["Summary"].str[:120]
                            st.dataframe(timeline, use_container_width=True, hide_index=True)

                            # AI Analysis button
                            btn_key = f"ai_{rep}_{dn_key}"
                            if st.button("🤖 Analyze Deal Health", key=btn_key):
                                with st.spinner("Analyzing..."):
                                    # Build context for Claude
                                    deal_info = f"Deal: {deal_row.get('deal_name', '')}\n"
                                    deal_info += f"Company: {deal_row.get('company_name', '')}\n"
                                    deal_info += f"Rep: {rep}\n"
                                    deal_info += f"Stage: {deal_row.get('deal_stage', '')}\n"
                                    deal_info += f"Forecast: {deal_row.get('forecast_category', '')}\n"
                                    deal_info += f"Amount: ${deal_row.get('amount', 0):,.0f}\n"
                                    deal_info += f"Close Date: {deal_row.get('close_date', '')}\n\n"
                                    deal_info += "Recent Activity (last 30 days):\n"
                                    for _, act in cached.iterrows():
                                        dt_str = act["_dt"].strftime("%m/%d") if pd.notna(act["_dt"]) else "?"
                                        deal_info += f"- {dt_str} | {act['_tp']} | {act['_owner']} | {act['_summary']}\n"

                                    try:
                                        import anthropic
                                        client = anthropic.Anthropic(api_key=st.secrets["ANTHROPIC_API_KEY"])
                                        response = client.messages.create(
                                            model="claude-sonnet-4-20250514",
                                            max_tokens=500,
                                            messages=[{"role": "user", "content": f"""You are a sales ops analyst. Based on this deal and its recent activity, give a brief assessment (3-5 sentences) covering:
1. Deal momentum (accelerating, stalling, or stalled)
2. Key risk factors
3. Recommended next action

{deal_info}"""}]
                                        )
                                        st.markdown(response.content[0].text)
                                    except Exception as e:
                                        st.warning(f"AI analysis unavailable: {e}")

        # Diagnostics
        unmatched = mg[mg["total"] == 0]
        deal_cos = set(mg["_co"].unique()) - {""}
        act_cos = set(all_act["_co"].unique()) - {""} if not all_act.empty else set()
        overlap = deal_cos & act_cos
        with st.expander("🔍 Company Name Match Diagnostics"):
            st.markdown(f"**Deals with activity match:** {len(matched_deals)} / {len(mg)}")
            st.markdown(f"**Unique companies in deals:** {len(deal_cos)}")
            st.markdown(f"**Unique companies in activity:** {len(act_cos)}")
            st.markdown(f"**Overlapping companies:** {len(overlap)}")
            if not unmatched.empty:
                st.markdown("**Unmatched deal companies** (no activity found):")
                unmatched_cos = unmatched[["company_name", "deal_name", "hubspot_owner_name"]].drop_duplicates() if all(c in unmatched.columns for c in ("company_name", "deal_name", "hubspot_owner_name")) else pd.DataFrame()
                if not unmatched_cos.empty:
                    st.dataframe(unmatched_cos.head(30), use_container_width=True, hide_index=True)
