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
    ft = _fdate_raw(_frep(data.tasks), "completed_at")
    fe = _fdate_raw(_frep(data.emails), "activity_date")
    total = len(fm) + len(fc) + len(ft) + len(fe)

    kpi([
        ("Total", f"{total:,}", ""),
        ("Meetings", f"{len(fm):,}", "green"),
        ("Calls", f"{len(fc):,}", "blue"),
        ("Emails", f"{len(fe):,}", "purple"),
        ("Tasks", f"{len(ft):,}", "amber"),
    ])

    # Leaderboard
    st.markdown('<div class="sec-title">Leaderboard</div>', unsafe_allow_html=True)

    rows = []
    for rep in selected_reps:
        m = len(fm[fm["hubspot_owner_name"] == rep]) if not fm.empty and "hubspot_owner_name" in fm.columns else 0
        c = len(fc[fc["hubspot_owner_name"] == rep]) if not fc.empty and "hubspot_owner_name" in fc.columns else 0
        e = len(fe[fe["hubspot_owner_name"] == rep]) if not fe.empty and "hubspot_owner_name" in fe.columns else 0
        comp, over = 0, 0
        if not ft.empty and "hubspot_owner_name" in ft.columns:
            rt = ft[ft["hubspot_owner_name"] == rep]
            if "task_status" in rt.columns and not rt.empty:
                u = rt["task_status"].astype(str).str.upper().str.strip()
                comp = int(u.isin({"COMPLETED", "COMPLETE", "DONE"}).sum())
                over = int(u.isin({"OVERDUE", "PAST_DUE", "DEFERRED"}).sum())
        score = m*WEIGHTS["meetings"] + c*WEIGHTS["calls"] + e*WEIGHTS["emails"] + comp*WEIGHTS["completed_tasks"] + over*WEIGHTS["overdue_tasks"]
        rows.append({"Rep": rep, "Meetings": m, "Calls": c, "Emails": e, "Tasks": comp, "Overdue": over, "Score": score})

    lb = pd.DataFrame(rows).sort_values("Score", ascending=False).reset_index(drop=True)
    st.dataframe(lb, use_container_width=True, hide_index=True)

    # Charts
    ch1, ch2 = st.columns(2)
    with ch1:
        st.markdown('<div class="sec-title">Activity by Rep</div>', unsafe_allow_html=True)
        if not lb.empty:
            fig = px.bar(
                lb.melt(id_vars="Rep", value_vars=["Meetings", "Calls", "Emails", "Tasks"],
                        var_name="Type", value_name="Count"),
                x="Rep", y="Count", color="Type", barmode="group",
                color_discrete_map={"Meetings": C["meetings"], "Calls": C["calls"],
                                    "Emails": C["emails"], "Tasks": C["tasks"]},
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
        with st.expander(f"**{rep}**  ·  {r['Meetings']} mtgs  ·  {r['Calls']} calls  ·  {r['Emails']} emails  ·  {r['Tasks']} tasks  ·  Score {r['Score']}"):
            t1, t2, t3, t4 = st.tabs(["🟢 Meetings", "🔵 Calls", "🟣 Emails", "🟡 Tasks"])

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
                    s = [c for c in ("completed_at", "task_title", "company_name", "task_status", "priority", "task_type") if c in rt.columns]
                    st.dataframe(_display_df(_safe_sort(rt[s].copy(), s[0]) if s else rt), use_container_width=True, hide_index=True)
                else: st.caption("No tasks.")


# ════════════════════════════════════════════════════════════════════════
# PAGE: DEAL HEALTH
# ════════════════════════════════════════════════════════════════════════
elif st.session_state.page == "deals":

    st.markdown("---")

    deals_f = _frep(_fpipe(data.deals))
    active = deals_f[~deals_f["is_terminal"]].copy() if "is_terminal" in deals_f.columns else deals_f.copy()
    am, ac, at, ae, an = _frep(data.meetings), _frep(data.calls), _frep(data.tasks), _frep(data.emails), _frep(data.notes)

    if active.empty:
        st.info("No active deals.")
    else:
        # Activity by company
        frames = []
        for df, typ, dc in [(ac, "Call", "activity_date"), (am, "Meeting", "meeting_start_time"), (at, "Task", "completed_at"), (ae, "Email", "activity_date"), (an, "Note", "activity_date")]:
            if df.empty or "company_name" not in df.columns: continue
            t = df[["company_name"]].copy()
            t["_dt"] = pd.to_datetime(df[dc], errors="coerce") if dc in df.columns else pd.NaT
            t["_tp"] = typ
            frames.append(t)

        now = pd.Timestamp.now()
        d7, d30 = now - pd.Timedelta(days=7), now - pd.Timedelta(days=30)

        if frames:
            aa = pd.concat(frames, ignore_index=True).dropna(subset=["company_name"])
            aa["_co"] = aa["company_name"].astype(str).str.strip().str.lower()
            cs = aa.groupby("_co").agg(
                last_act=("_dt", "max"), total=("_dt", "count"),
                a7=("_dt", lambda x: (x >= d7).sum()), a30=("_dt", lambda x: (x >= d30).sum()),
                calls=("_tp", lambda x: (x == "Call").sum()),
                mtgs=("_tp", lambda x: (x == "Meeting").sum()),
                emails=("_tp", lambda x: (x == "Email").sum()),
                tasks=("_tp", lambda x: (x == "Task").sum()),
                notes=("_tp", lambda x: (x == "Note").sum()),
            ).reset_index()
        else:
            cs = pd.DataFrame(columns=["_co"])

        active["_co"] = active["company_name"].astype(str).str.strip().str.lower() if "company_name" in active.columns else ""
        mg = active.merge(cs, on="_co", how="left")

        for col in ["total", "a7", "a30", "calls", "mtgs", "emails", "tasks", "notes"]:
            if col in mg.columns: mg[col] = mg[col].fillna(0).astype(int)

        mg["health"] = mg.get("last_act", pd.Series(dtype="datetime64[ns]")).apply(
            lambda x: "Active" if pd.notna(x) and x >= d7 else ("Stale" if pd.notna(x) and x >= d30 else ("Inactive" if pd.notna(x) else "No Activity"))
        )
        mg["days_idle"] = mg.get("last_act", pd.Series(dtype="datetime64[ns]")).apply(
            lambda x: (now - x).days if pd.notna(x) else None
        )

        na = len(mg[mg["health"] == "Active"])
        nw = len(mg) - na
        kpi([
            ("Active Deals", f"{len(mg):,}", ""),
            ("Pipeline", f"${mg['amount'].sum():,.0f}" if "amount" in mg.columns else "$0", "blue"),
            ("Engaged 7d", f"{na}", "green"),
            ("Needs Attention", f"{nw}", "red"),
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

        # Per-rep
        st.markdown('<div class="sec-title">Deals by Rep</div>', unsafe_allow_html=True)
        for rep in selected_reps:
            rd = mg[mg["hubspot_owner_name"] == rep] if "hubspot_owner_name" in mg.columns else pd.DataFrame()
            if rd.empty: continue
            n = len(rd)
            v = rd["amount"].sum() if "amount" in rd.columns else 0
            nok = len(rd[rd["health"] == "Active"])

            with st.expander(f"**{rep}**  ·  {n} deals  ·  ${v:,.0f}  ·  {nok} active  ·  {n - nok} attention"):
                sc = [c for c in ("deal_name", "company_name", "deal_stage", "forecast_category",
                                  "amount", "close_date", "health", "days_idle",
                                  "calls", "mtgs", "emails", "notes", "tasks", "a30") if c in rd.columns]
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
                        "notes": "Notes", "tasks": "Tasks",
                        "a30": st.column_config.NumberColumn("30d"),
                    })

                # Show recent notes for this rep's deals
                rep_notes = an[an["hubspot_owner_name"] == rep] if not an.empty and "hubspot_owner_name" in an.columns else pd.DataFrame()
                if not rep_notes.empty and "deal_name" in rep_notes.columns:
                    deal_names = set(rd["deal_name"].dropna().astype(str)) if "deal_name" in rd.columns else set()
                    matched = rep_notes[rep_notes["deal_name"].astype(str).isin(deal_names)]
                    if not matched.empty:
                        st.markdown("**📝 Recent Notes**")
                        note_cols = [c for c in ("activity_date", "deal_name", "company_name", "note_body") if c in matched.columns]
                        st.dataframe(_display_df(_safe_sort(matched[note_cols].copy(), note_cols[0])),
                                     use_container_width=True, hide_index=True)
