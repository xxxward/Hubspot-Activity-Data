"""
Calyx Activity Hub — HubSpot Sales Analytics
Complete UI Overhaul — Vibrant Neon Dark Theme
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

st.set_page_config(
    page_title="Calyx Activity Hub",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ════════════════════════════════════════════════════════════════════════
# THEME — Vibrant Neon Dark
# ════════════════════════════════════════════════════════════════════════
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

:root {
    --bg-primary: #0c0a1a;
    --bg-card: #151228;
    --bg-elevated: #1e1a35;
    --border: #2d2750;
    --text-primary: #ede9fc;
    --text-secondary: #9b93b7;
    --text-muted: #6a6283;
    --pink: #f472b6;
    --blue: #818cf8;
    --purple: #c084fc;
    --amber: #fbbf24;
    --red: #fb7185;
    --cyan: #67e8f9;
    --violet: #a78bfa;
    --green: #34d399;
}

/* ── Base ── */
.stApp {
    background: var(--bg-primary) !important;
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
}
.block-container { padding-top: 1.2rem !important; }

/* Filter area spacing */
.filter-spacer { margin-top: 16px; }
.stExpander[data-testid="stExpander"] {
    margin-top: 8px !important;
}

/* ── Sidebar ── */
section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0e0b1e 0%, #130f26 50%, #0e0b1e 100%) !important;
    border-right: 1px solid var(--border) !important;
}
section[data-testid="stSidebar"] * { color: var(--text-primary) !important; }
section[data-testid="stSidebar"] .stCaption * { color: var(--text-muted) !important; }

/* ── Global text ── */
.stApp, .stApp p, .stApp span, .stApp label, .stApp li,
.stMarkdown, .stMarkdown p, .stMarkdown span,
.stExpander summary, .stExpander summary span,
.stExpander [data-testid="stExpanderDetails"] p,
details summary span { color: var(--text-primary) !important; }

/* ── Brand ── */
.brand-title {
    font-size: 1.25rem;
    font-weight: 800;
    letter-spacing: -0.5px;
    background: linear-gradient(135deg, #818cf8 0%, #c084fc 50%, #f472b6 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    margin-bottom: 2px;
    line-height: 1.3;
}
.brand-sub {
    font-size: 0.68rem;
    color: var(--text-muted);
    letter-spacing: 1.5px;
    text-transform: uppercase;
    margin-bottom: 8px;
}

/* ── Nav Items ── */
.nav-section-label {
    font-size: 0.62rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 2px;
    color: var(--text-muted);
    padding: 16px 0 6px 4px;
}
.nav-item {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 10px 14px;
    border-radius: 10px;
    cursor: pointer;
    margin-bottom: 3px;
    transition: all 0.15s ease;
    text-decoration: none;
    border-left: 3px solid transparent;
}
.nav-item:hover {
    background: var(--bg-elevated);
}
.nav-item.active {
    background: var(--bg-elevated);
    border-left: 3px solid;
    border-image: linear-gradient(180deg, #818cf8, #c084fc, #f472b6) 1;
}
.nav-item .nav-label {
    font-size: 0.82rem;
    font-weight: 600;
    color: var(--text-secondary);
}
.nav-item.active .nav-label {
    color: var(--text-primary);
}
.nav-item .nav-badge {
    font-size: 0.65rem;
    font-weight: 600;
    color: var(--text-muted);
    background: rgba(45, 39, 80, 0.6);
    padding: 2px 8px;
    border-radius: 10px;
}
.nav-item.active .nav-badge {
    background: rgba(129, 140, 248, 0.15);
    color: var(--violet);
}

/* ── Sidebar footer ── */
.sidebar-footer {
    font-size: 0.65rem;
    color: var(--text-muted);
    line-height: 1.6;
    padding: 12px 4px;
    border-top: 1px solid var(--border);
    margin-top: 12px;
}

/* ── KPI Cards ── */
.kpi-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(155px, 1fr));
    gap: 14px;
    margin: 16px 0 20px;
}
.kpi {
    background: linear-gradient(135deg, #151228 0%, #1a1530 100%);
    border: 1px solid var(--border);
    border-radius: 14px;
    padding: 20px 18px 16px;
    position: relative;
    overflow: hidden;
    transition: all 0.2s ease;
}
.kpi:hover {
    box-shadow: 0 4px 24px rgba(129, 140, 248, 0.08);
    border-color: #3d3566;
}
.kpi::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 3px;
    border-radius: 14px 14px 0 0;
}
.kpi.pink::before { background: var(--pink); }
.kpi.blue::before { background: var(--blue); }
.kpi.purple::before { background: var(--purple); }
.kpi.amber::before { background: var(--amber); }
.kpi.red::before { background: var(--red); }
.kpi.cyan::before { background: var(--cyan); }
.kpi.violet::before { background: var(--violet); }
.kpi.green::before { background: var(--green); }
.kpi.gradient::before { background: linear-gradient(135deg, #818cf8, #c084fc, #f472b6); }

.kpi-label {
    font-size: 0.68rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 1.2px;
    color: var(--text-secondary);
    margin-bottom: 8px;
}
.kpi-val {
    font-size: 2rem;
    font-weight: 800;
    color: var(--text-primary);
    line-height: 1;
}
.kpi.pink .kpi-val { color: var(--pink); }
.kpi.blue .kpi-val { color: var(--blue); }
.kpi.purple .kpi-val { color: var(--purple); }
.kpi.amber .kpi-val { color: var(--amber); }
.kpi.red .kpi-val { color: var(--red); }
.kpi.cyan .kpi-val { color: var(--cyan); }
.kpi.violet .kpi-val { color: var(--violet); }
.kpi.green .kpi-val { color: var(--green); }

.kpi-delta {
    font-size: 0.7rem;
    font-weight: 600;
    margin-top: 6px;
}
.kpi-delta.up { color: var(--green); }
.kpi-delta.down { color: var(--red); }
.kpi-delta.neutral { color: var(--text-muted); }

/* ── Section Headers ── */
.sec-header {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 8px 0 4px;
    margin: 6px 0 2px;
}
.sec-header .sec-icon {
    font-size: 1.1rem;
}
.sec-header .sec-title {
    font-size: 0.82rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 1.5px;
    color: var(--text-secondary);
}
.sec-header .sec-accent {
    flex: 0 0 3px;
    height: 18px;
    border-radius: 2px;
}
.sec-subtitle {
    font-size: 0.78rem;
    color: var(--text-muted);
    font-style: italic;
    margin: -2px 0 14px 0;
    padding-left: 2px;
}

/* ── Page Header ── */
.page-header {
    padding: 8px 0 2px;
}
.page-header h1 {
    font-size: 1.5rem;
    font-weight: 800;
    color: var(--text-primary);
    margin: 0;
    line-height: 1.2;
}
.page-header .page-sub {
    font-size: 0.82rem;
    color: var(--text-muted);
    font-style: italic;
    margin: 4px 0 0;
}

/* ── Dividers ── */
.section-divider {
    height: 1px;
    background: linear-gradient(90deg, transparent, var(--border), transparent);
    margin: 24px 0 20px;
}

/* ── Rep Spotlight Cards ── */
.rep-card {
    background: linear-gradient(135deg, #151228 0%, #1a1530 100%);
    border: 1px solid var(--border);
    border-radius: 14px;
    padding: 20px;
    transition: all 0.2s ease;
}
.rep-card:hover {
    box-shadow: 0 4px 24px rgba(129, 140, 248, 0.1);
    border-color: #3d3566;
}
.rep-avatar {
    width: 42px;
    height: 42px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 0.85rem;
    font-weight: 800;
    color: #0c0a1a;
    margin-bottom: 10px;
}
.rep-card .rep-name {
    font-size: 0.9rem;
    font-weight: 700;
    color: var(--text-primary);
    margin-bottom: 4px;
}
.rep-card .rep-stats {
    font-size: 0.72rem;
    color: var(--text-secondary);
    line-height: 1.6;
}
.rep-card .rep-score {
    font-size: 1.4rem;
    font-weight: 800;
    color: var(--violet);
    margin-top: 8px;
}
.health-badge {
    display: inline-block;
    font-size: 0.62rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.8px;
    padding: 3px 8px;
    border-radius: 6px;
    margin-top: 6px;
}
.health-badge.improving { background: rgba(52, 211, 153, 0.15); color: var(--green); }
.health-badge.active { background: rgba(129, 140, 248, 0.15); color: var(--blue); }
.health-badge.declining { background: rgba(251, 113, 133, 0.15); color: var(--red); }

/* ── Empty States ── */
.empty-state {
    text-align: center;
    padding: 40px 20px;
    color: var(--text-muted);
    font-size: 0.85rem;
}
.empty-state .empty-icon { font-size: 2rem; margin-bottom: 8px; }

/* ── Filter bar ── */
.filter-indicator {
    display: inline-block;
    font-size: 0.65rem;
    font-weight: 600;
    color: var(--violet);
    background: rgba(167, 139, 250, 0.12);
    padding: 3px 10px;
    border-radius: 8px;
    margin-left: 8px;
}
.chip-container {
    display: flex;
    gap: 6px;
    flex-wrap: wrap;
    margin: 6px 0 2px;
}
.chip {
    font-size: 0.68rem;
    font-weight: 600;
    padding: 4px 12px;
    border-radius: 8px;
    border: 1px solid var(--border);
    color: var(--text-secondary);
    background: transparent;
    cursor: pointer;
    transition: all 0.15s ease;
}
.chip:hover, .chip.active {
    background: var(--bg-elevated);
    border-color: var(--violet);
    color: var(--text-primary);
}

/* ── Leaderboard ── */
.lb-rank { font-size: 1.1rem; }

/* ── Misc ── */
.stExpander {
    border: 1px solid var(--border) !important;
    border-radius: 12px !important;
    overflow: hidden;
    background: var(--bg-card) !important;
}
.stTabs [data-baseweb="tab"] { color: var(--text-secondary) !important; font-weight: 500; }
.stTabs [aria-selected="true"] { color: var(--violet) !important; }
hr { border-color: var(--border) !important; }
.stDataFrame { border-radius: 10px; overflow: hidden; }
.stMultiSelect > div { max-height: none !important; }
div[data-baseweb="select"] > div { flex-wrap: wrap !important; }

/* Fix widget labels */
.stDateInput label, .stMultiSelect label, .stSelectbox label {
    color: var(--text-secondary) !important;
    font-size: 0.72rem !important;
    font-weight: 600 !important;
    text-transform: uppercase !important;
    letter-spacing: 1px !important;
}

/* Expander header fixes */
.stExpander details summary {
    background: var(--bg-card) !important;
}
</style>
""", unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════════════════
# PLOTLY THEME HELPER
# ════════════════════════════════════════════════════════════════════════
def styled_fig(fig, height=340):
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="#151228",
        font=dict(color="#9b93b7", family="Inter, sans-serif", size=11),
        xaxis=dict(gridcolor="#1e1a35", zerolinecolor="#1e1a35", tickfont=dict(size=10, color="#9b93b7")),
        yaxis=dict(gridcolor="#1e1a35", zerolinecolor="#1e1a35", tickfont=dict(size=10, color="#9b93b7")),
        margin=dict(l=40, r=16, t=32, b=48),
        legend=dict(bgcolor="rgba(0,0,0,0)", orientation="h", y=-0.18, font=dict(size=10, color="#9b93b7")),
        showlegend=True,
        height=height,
        bargap=0.3,
        hoverlabel=dict(bgcolor="#1e1a35", bordercolor="#2d2750", font=dict(color="#ede9fc", size=12)),
    )
    return fig


# ── Color map (consistent everywhere) ──────────────────────────────────
C = {
    "meetings": "#f472b6", "calls": "#818cf8", "emails": "#c084fc",
    "tasks": "#fbbf24", "completed_tasks": "#fbbf24", "notes": "#9b93b7",
    "tickets": "#fb7185", "overdue": "#fb7185",
    "active": "#34d399", "stale": "#fbbf24", "inactive": "#fb7185", "none": "#6a6283",
    "gong": "#67e8f9", "score": "#a78bfa",
}

# Activity → accent class for KPI cards
ACCENT = {
    "meetings": "pink", "calls": "blue", "emails": "purple",
    "tasks": "amber", "tickets": "red", "notes": "violet",
}


# ════════════════════════════════════════════════════════════════════════
# DATA LOADING
# ════════════════════════════════════════════════════════════════════════
@st.cache_data(ttl=600, show_spinner="Loading data...")
def get_data():
    d = load_all()
    return {f: getattr(d, f) for f in d.__dataclass_fields__}

try:
    data = AnalyticsData(**get_data())
    if "last_refresh" not in st.session_state:
        st.session_state["last_refresh"] = datetime.now()
except Exception as e:
    st.error(f"**Data load failed:** {e}")
    st.stop()


# ════════════════════════════════════════════════════════════════════════
# SIDEBAR — Navigation
# ════════════════════════════════════════════════════════════════════════
NAV_SECTIONS = [
    ("command", "🏠", "Command Center"),
    ("calls",   "📞", "Calls"),
    ("meetings","📅", "Meetings"),
    ("tasks",   "✅", "Tasks"),
    ("tickets", "🎫", "Tickets"),
    ("deals",   "🏥", "Deal Health"),
]

# Count badges
_counts = {
    "command": None,
    "calls": len(data.calls) if not data.calls.empty else 0,
    "meetings": len(data.meetings) if not data.meetings.empty else 0,
    "tasks": len(data.tasks) if not data.tasks.empty else 0,
    "tickets": len(data.tickets) if not data.tickets.empty else 0,
    "deals": len(data.deals) if not data.deals.empty else 0,
}

if "page" not in st.session_state:
    st.session_state.page = "command"

with st.sidebar:
    st.markdown('<div class="brand-title">Calyx Activity Hub</div>', unsafe_allow_html=True)
    st.markdown('<div class="brand-sub">HubSpot Analytics</div>', unsafe_allow_html=True)

    st.markdown('<div class="nav-section-label">Navigation</div>', unsafe_allow_html=True)

    for key, icon, label in NAV_SECTIONS:
        active_cls = "active" if st.session_state.page == key else ""
        badge = f' · {_counts[key]:,}' if _counts[key] is not None else ""
        badge_html = f'<span class="nav-badge">{_counts[key]:,}</span>' if _counts[key] is not None else ""

        # Use st.button for each nav item
        if st.button(f"{icon}  {label}{badge}", key=f"nav_{key}", use_container_width=True,
                     type="primary" if st.session_state.page == key else "secondary"):
            st.session_state.page = key
            st.rerun()

    # Refresh button
    st.markdown("---")
    if st.button("🔄  Refresh Data", key="refresh_data", use_container_width=True):
        get_data.clear()
        st.session_state["last_refresh"] = datetime.now()
        st.rerun()

    # Footer
    last_refresh = st.session_state.get("last_refresh", datetime.now())
    refresh_str = last_refresh.strftime("%b %d, %I:%M %p")
    st.markdown(f"""<div class="sidebar-footer">
        ⏱ Last refreshed: {refresh_str}<br>
        {len(data.deals)} deals · {len(data.calls)} calls · {len(data.meetings)} mtgs<br>
        {len(data.emails)} emails · {len(data.tasks)} tasks · {len(data.tickets)} tickets
    </div>""", unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════════════════
# GLOBAL FILTER BAR
# ════════════════════════════════════════════════════════════════════════
_default_start = date.today() - timedelta(days=7)

st.markdown('<div class="filter-spacer"></div>', unsafe_allow_html=True)
with st.expander("🔎 Filters", expanded=False):
    # Quick-select chips
    chip_col, _, _ = st.columns([3, 1, 1])
    with chip_col:
        quick = st.radio(
            "Quick range",
            ["Today", "7d", "30d", "90d", "This Quarter", "This Year", "All Time", "Custom"],
            horizontal=True, index=1, label_visibility="collapsed",
        )
    today = date.today()
    if quick == "Today":
        start_date, end_date = today, today
    elif quick == "7d":
        start_date, end_date = today - timedelta(days=7), today
    elif quick == "30d":
        start_date, end_date = today - timedelta(days=30), today
    elif quick == "90d":
        start_date, end_date = today - timedelta(days=90), today
    elif quick == "This Quarter":
        q_start_month = ((today.month - 1) // 3) * 3 + 1
        start_date = date(today.year, q_start_month, 1)
        end_date = today
    elif quick == "This Year":
        start_date, end_date = date(today.year, 1, 1), today
    elif quick == "All Time":
        start_date, end_date = date(2020, 1, 1), today
    else:
        date_range = st.date_input("📅 Date Range", value=(_default_start, today), max_value=today)
        start_date, end_date = (date_range if isinstance(date_range, tuple) and len(date_range) == 2 else (_default_start, today))

    fc1, fc2, fc3 = st.columns([2, 2, 1])
    with fc1:
        selected_reps = st.multiselect("👤 Sales Reps", REPS_IN_SCOPE, default=REPS_IN_SCOPE)
    with fc2:
        if st.session_state.page == "deals":
            selected_pipelines = st.multiselect("🔀 Pipelines", PIPELINES_IN_SCOPE, default=PIPELINES_IN_SCOPE)
        else:
            selected_pipelines = PIPELINES_IN_SCOPE
    with fc3:
        st.markdown("<br>", unsafe_allow_html=True)
        is_filtered = (len(selected_reps) < len(REPS_IN_SCOPE)) or quick != "7d"
        if is_filtered:
            st.markdown('<span class="filter-indicator">⚡ Filters active</span>', unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS (logic preserved)
# ════════════════════════════════════════════════════════════════════════
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
            mask = dt.notna() & (dt >= pd.Timestamp(start_date)) & (dt <= pd.Timestamp(end_date) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1))
            return df[mask].copy()
    return df

def _fdate(df, col="period_day"):
    if df.empty or col not in df.columns: return df
    dt = pd.to_datetime(df[col], errors="coerce")
    return df[(dt >= pd.Timestamp(start_date)) & (dt <= pd.Timestamp(end_date) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1))].copy()

def _safe_sort(df, col, asc=False):
    try: return df.sort_values(col, ascending=asc)
    except: return df

def _display_df(df):
    """Clean a DataFrame for st.dataframe — fix mixed types that break PyArrow."""
    df = df.copy()
    for col in df.columns:
        if df[col].dtype == object:
            has_ts = df[col].apply(lambda x: isinstance(x, pd.Timestamp)).any()
            if has_ts:
                df[col] = pd.to_datetime(df[col], errors="coerce").dt.strftime("%Y-%m-%d %H:%M").fillna("")
    return df

def kpi(cards):
    """Render KPI card grid. cards: list of (label, value, accent_class) or (label, value, accent, delta_str)."""
    html = '<div class="kpi-grid">'
    for item in cards:
        label, val, accent = item[0], item[1], item[2]
        delta = item[3] if len(item) > 3 else None
        cls = f"kpi {accent}" if accent else "kpi"
        delta_html = ""
        if delta:
            if delta.startswith("▲"):
                delta_html = f'<div class="kpi-delta up">{delta}</div>'
            elif delta.startswith("▼"):
                delta_html = f'<div class="kpi-delta down">{delta}</div>'
            else:
                delta_html = f'<div class="kpi-delta neutral">{delta}</div>'
        html += f'<div class="{cls}"><div class="kpi-label">{label}</div><div class="kpi-val">{val}</div>{delta_html}</div>'
    html += '</div>'
    st.markdown(html, unsafe_allow_html=True)

def hs_deal_url(did):
    if pd.isna(did) or not str(did).strip(): return ""
    return f"https://app.hubspot.com/contacts/44704741/deal/{int(float(str(did)))}"

def section_header(icon, title, accent_color=None):
    accent = f'background: {accent_color};' if accent_color else 'background: var(--violet);'
    st.markdown(f'''<div class="sec-header">
        <span class="sec-accent" style="{accent}"></span>
        <span class="sec-icon">{icon}</span>
        <span class="sec-title">{title}</span>
    </div>''', unsafe_allow_html=True)

def section_divider():
    st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)

def empty_state(msg="Nothing here yet — check your date range? 🤔"):
    st.markdown(f'<div class="empty-state"><div class="empty-icon">🔍</div>{msg}</div>', unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════════════════
# FILTERED DATA (shared across pages)
# ════════════════════════════════════════════════════════════════════════
fm = _fdate_raw(_frep(data.meetings), "meeting_start_time")
fc = _fdate_raw(_frep(data.calls), "activity_date")
fe = _fdate_raw(_frep(data.emails), "activity_date")
fn = _fdate_raw(_frep(data.notes), "activity_date")
fk = _fdate_raw(_frep(data.tickets), "created_date")

# Tasks: try activity_date first, then created_date, then due_date
ft_all = _frep(data.tasks)
if not ft_all.empty:
    task_dt = pd.Series(pd.NaT, index=ft_all.index)
    for try_col in ("activity_date", "created_date", "due_date", "completed_at"):
        if try_col in ft_all.columns:
            candidate = pd.to_datetime(ft_all[try_col], errors="coerce")
            task_dt = task_dt.fillna(candidate)
    ft = ft_all[task_dt.notna() & (task_dt >= pd.Timestamp(start_date)) & (task_dt <= pd.Timestamp(end_date) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1))].copy()
else:
    ft = ft_all

total_activities = len(fm) + len(fc) + len(ft) + len(fe) + len(fn) + len(fk)


# ════════════════════════════════════════════════════════════════════════
# LEADERBOARD COMPUTATION (reused across pages)
# ════════════════════════════════════════════════════════════════════════
def build_leaderboard():
    rows = []
    for rep in selected_reps:
        m = len(fm[fm["hubspot_owner_name"] == rep]) if not fm.empty and "hubspot_owner_name" in fm.columns else 0
        c = len(fc[fc["hubspot_owner_name"] == rep]) if not fc.empty and "hubspot_owner_name" in fc.columns else 0
        e = len(fe[fe["hubspot_owner_name"] == rep]) if not fe.empty and "hubspot_owner_name" in fe.columns else 0
        n = len(fn[fn["hubspot_owner_name"] == rep]) if not fn.empty and "hubspot_owner_name" in fn.columns else 0
        k = len(fk[fk["hubspot_owner_name"] == rep]) if not fk.empty and "hubspot_owner_name" in fk.columns else 0

        comp, over = 0, 0
        if not ft.empty and "hubspot_owner_name" in ft.columns:
            rt = ft[ft["hubspot_owner_name"] == rep]
            if not rt.empty and "task_status" in rt.columns:
                status = rt["task_status"].astype(str).str.upper().str.strip()
                comp = int(status.isin({"COMPLETED", "COMPLETE", "DONE"}).sum())
                if "due_date" in rt.columns:
                    due = pd.to_datetime(rt["due_date"], errors="coerce")
                    not_done = ~status.isin({"COMPLETED", "COMPLETE", "DONE"})
                    past_due = due.notna() & (due < pd.Timestamp(date.today()))
                    over = int((not_done & past_due).sum())

        score = m*WEIGHTS["meetings"] + c*WEIGHTS["calls"] + e*WEIGHTS["emails"] + comp*WEIGHTS["completed_tasks"] + over*WEIGHTS["overdue_tasks"]
        rows.append({"Rep": rep, "Meetings": m, "Calls": c, "Emails": e, "Tasks": comp,
                     "Overdue": over, "Notes": n, "Tickets": k, "Score": round(score, 1)})

    return pd.DataFrame(rows).sort_values("Score", ascending=False).reset_index(drop=True)

lb = build_leaderboard()


# ════════════════════════════════════════════════════════════════════════
# PAGE: 🏠 COMMAND CENTER
# ════════════════════════════════════════════════════════════════════════
if st.session_state.page == "command":

    st.markdown("""<div class="page-header">
        <h1>🏠 Command Center</h1>
        <p class="page-sub">Your team's pulse, at a glance.</p>
    </div>""", unsafe_allow_html=True)

    # Easter egg
    if total_activities == 0:
        st.markdown("""<div class="empty-state" style="padding:60px 20px;">
            <div class="empty-icon">🏝️</div>
            The team's on vacation... or something's broken.
        </div>""", unsafe_allow_html=True)
        st.stop()

    # ── Row 1: Hero KPIs ──
    kpi([
        ("Total Activities", f"{total_activities:,}", "gradient"),
        ("Meetings", f"{len(fm):,}", "pink"),
        ("Calls", f"{len(fc):,}", "blue"),
        ("Emails", f"{len(fe):,}", "purple"),
        ("Tasks", f"{len(ft):,}", "amber"),
        ("Tickets", f"{len(fk):,}", "red"),
    ])

    section_divider()

    # ── Row 2: Leaderboard + Activity Mix ──
    col_lb, col_mix = st.columns([3, 2])

    with col_lb:
        section_header("🏆", "Team Leaderboard", C["score"])
        if not lb.empty:
            lb_display = lb.copy()
            rank_icons = {0: "🥇", 1: "🥈", 2: "🥉"}
            lb_display.insert(0, "Rank", [rank_icons.get(i, f"#{i+1}") for i in range(len(lb_display))])
            st.dataframe(lb_display, use_container_width=True, hide_index=True,
                         column_config={
                             "Score": st.column_config.NumberColumn("Score", format="%.1f"),
                             "Overdue": st.column_config.NumberColumn("Overdue ⚠️"),
                         })
        else:
            empty_state()

    with col_mix:
        section_header("🍩", "Activity Mix", C["emails"])
        mix_data = pd.DataFrame({
            "Type": ["Meetings", "Calls", "Emails", "Tasks", "Tickets", "Notes"],
            "Count": [len(fm), len(fc), len(fe), len(ft), len(fk), len(fn)],
        })
        mix_data = mix_data[mix_data["Count"] > 0]
        if not mix_data.empty:
            fig_mix = px.pie(
                mix_data, names="Type", values="Count", hole=0.55,
                color="Type",
                color_discrete_map={
                    "Meetings": C["meetings"], "Calls": C["calls"], "Emails": C["emails"],
                    "Tasks": C["tasks"], "Tickets": C["tickets"], "Notes": C["notes"],
                },
            )
            fig_mix.update_traces(textinfo="label+value", textfont=dict(color="#ede9fc", size=11),
                                  marker=dict(line=dict(color="#0c0a1a", width=2)))
            st.plotly_chart(styled_fig(fig_mix, 320), use_container_width=True)
        else:
            empty_state("All quiet on the western front. 🤠")

    section_divider()

    # ── Row 3: Daily Activity Trend ──
    section_header("📈", "Daily Activity Trend", C["calls"])
    daily = _fdate(_frep(data.activity_counts_daily), "period_day")
    if not daily.empty:
        mcols = [c for c in ("meetings", "calls", "emails", "completed_tasks") if c in daily.columns]
        if mcols and "period_day" in daily.columns:
            trend = daily.groupby("period_day", dropna=False)[mcols].sum().reset_index()
            trend["period_day"] = pd.to_datetime(trend["period_day"])
            fig_trend = px.area(
                trend.melt(id_vars="period_day", value_vars=mcols, var_name="Type", value_name="Count"),
                x="period_day", y="Count", color="Type",
                color_discrete_map={
                    "meetings": C["meetings"], "calls": C["calls"],
                    "emails": C["emails"], "completed_tasks": C["tasks"],
                },
            )
            fig_trend.update_traces(line_width=2, fill="tonexty", opacity=0.7)
            fig_trend.update_layout(xaxis_title="", yaxis_title="")
            st.plotly_chart(styled_fig(fig_trend, 300), use_container_width=True)
    else:
        empty_state("No daily data for this range.")

    section_divider()

    # ── Row 4: Rep Spotlight Cards ──
    section_header("👥", "Rep Spotlight", C["meetings"])

    if not lb.empty:
        rep_colors = ["#f472b6", "#818cf8", "#c084fc", "#fbbf24", "#67e8f9", "#a78bfa"]
        cols = st.columns(min(3, len(lb)))
        for i, (_, r) in enumerate(lb.iterrows()):
            rep = r["Rep"]
            initials = "".join([w[0] for w in rep.split()[:2]]).upper()
            color = rep_colors[i % len(rep_colors)]
            total_rep = r["Meetings"] + r["Calls"] + r["Emails"] + r["Tasks"] + r["Notes"] + r["Tickets"]

            # Simple trend indicator
            if r["Score"] > 30:
                health_cls, health_text = "improving", "🔥 Hot"
            elif r["Score"] > 15:
                health_cls, health_text = "active", "✅ Active"
            else:
                health_cls, health_text = "declining", "⚡ Needs Push"

            with cols[i % len(cols)]:
                st.markdown(f"""<div class="rep-card">
                    <div class="rep-avatar" style="background:{color};">{initials}</div>
                    <div class="rep-name">{rep}</div>
                    <div class="rep-stats">
                        {r['Meetings']} mtgs · {r['Calls']} calls · {r['Emails']} emails<br>
                        {r['Tasks']} tasks · {r['Overdue']} overdue · {total_rep} total
                    </div>
                    <div class="rep-score">{r['Score']}</div>
                    <div class="health-badge {health_cls}">{health_text}</div>
                </div>""", unsafe_allow_html=True)
                st.markdown("")  # spacer


# ════════════════════════════════════════════════════════════════════════
# PAGE: 📞 CALLS
# ════════════════════════════════════════════════════════════════════════
elif st.session_state.page == "calls":

    st.markdown("""<div class="page-header">
        <h1>📞 Calls</h1>
        <p class="page-sub">Every ring, every conversation.</p>
    </div>""", unsafe_allow_html=True)

    if fc.empty:
        empty_state("No calls found in this range. Time to dial! 📱")
    else:
        # KPIs
        n_calls = len(fc)
        n_inbound = len(fc[fc["call_direction"].str.upper().str.strip() == "INBOUND"]) if "call_direction" in fc.columns else 0
        n_outbound = n_calls - n_inbound
        ratio_str = f"{n_inbound}:{n_outbound}"
        avg_dur = fc["call_duration"].mean() if "call_duration" in fc.columns and fc["call_duration"].notna().any() else 0
        avg_dur_str = f"{avg_dur:.0f}s" if avg_dur else "—"

        kpi([
            ("Total Calls", f"{n_calls:,}", "blue"),
            ("In / Out", ratio_str, "purple"),
            ("Avg Duration", avg_dur_str, "cyan"),
            ("Outbound", f"{n_outbound:,}", "violet"),
        ])

        section_divider()

        # Charts
        ch1, ch2 = st.columns(2)
        with ch1:
            section_header("📊", "Calls by Outcome", C["calls"])
            if "call_outcome" in fc.columns:
                outcome = fc["call_outcome"].value_counts().reset_index()
                outcome.columns = ["Outcome", "Count"]
                fig = px.bar(outcome, y="Outcome", x="Count", orientation="h",
                             color_discrete_sequence=[C["calls"]])
                fig.update_layout(xaxis_title="", yaxis_title="")
                st.plotly_chart(styled_fig(fig, 280), use_container_width=True)

        with ch2:
            section_header("👤", "Calls by Rep", C["calls"])
            if "hubspot_owner_name" in fc.columns:
                by_rep = fc["hubspot_owner_name"].value_counts().reset_index()
                by_rep.columns = ["Rep", "Count"]
                fig = px.bar(by_rep, x="Rep", y="Count", color_discrete_sequence=[C["calls"]])
                fig.update_layout(xaxis_title="", yaxis_title="")
                st.plotly_chart(styled_fig(fig, 280), use_container_width=True)

        section_divider()

        # Direction breakdown
        if "call_direction" in fc.columns:
            section_header("↔️", "Inbound vs Outbound", C["calls"])
            dir_data = fc["call_direction"].value_counts().reset_index()
            dir_data.columns = ["Direction", "Count"]
            fig_dir = px.pie(dir_data, names="Direction", values="Count", hole=0.5,
                             color_discrete_sequence=[C["calls"], C["emails"]])
            fig_dir.update_traces(textinfo="label+percent", textfont=dict(color="#ede9fc", size=11))
            st.plotly_chart(styled_fig(fig_dir, 260), use_container_width=True)

        section_divider()

        # Detail table
        section_header("📋", "All Calls", C["calls"])
        call_cols = [c for c in ("activity_date", "hubspot_owner_name", "company_name", "call_direction",
                                  "call_outcome", "call_duration", "call_and_meeting_type") if c in fc.columns]
        if call_cols:
            st.dataframe(_display_df(_safe_sort(fc[call_cols].copy(), call_cols[0])),
                         use_container_width=True, hide_index=True)


# ════════════════════════════════════════════════════════════════════════
# PAGE: 📅 MEETINGS
# ════════════════════════════════════════════════════════════════════════
elif st.session_state.page == "meetings":

    st.markdown("""<div class="page-header">
        <h1>📅 Meetings</h1>
        <p class="page-sub">Face time that moves deals forward.</p>
    </div>""", unsafe_allow_html=True)

    if fm.empty:
        empty_state("No meetings in this range. Time to get face-to-face! 🤝")
    else:
        n_mtgs = len(fm)
        n_completed = len(fm[fm["meeting_outcome"].str.upper().str.strip() == "COMPLETED"]) if "meeting_outcome" in fm.columns else 0
        completion_rate = f"{n_completed/n_mtgs*100:.0f}%" if n_mtgs > 0 else "—"

        # Avg duration (excluding >480 min)
        avg_dur_val = "—"
        if "meeting_start_time" in fm.columns and "meeting_end_time" in fm.columns:
            ms = pd.to_datetime(fm["meeting_start_time"], errors="coerce")
            me = pd.to_datetime(fm["meeting_end_time"], errors="coerce")
            dur = (me - ms).dt.total_seconds() / 60
            dur_valid = dur[(dur > 0) & (dur <= 480)]
            if len(dur_valid) > 0:
                avg_dur_val = f"{dur_valid.mean():.0f} min"

        gong_rate = "—"
        if "has_gong" in fm.columns:
            gong_true = fm["has_gong"].sum()
            gong_rate = f"{gong_true/n_mtgs*100:.0f}%" if n_mtgs > 0 else "—"

        n_companies = fm["company_name"].nunique() if "company_name" in fm.columns else 0

        kpi([
            ("Total Meetings", f"{n_mtgs:,}", "pink"),
            ("Completion Rate", completion_rate, "green"),
            ("Avg Duration", avg_dur_val, "purple"),
            ("Gong Coverage", gong_rate, "cyan"),
            ("Companies", f"{n_companies:,}", "violet"),
        ])

        section_divider()

        # 2x2 charts
        r1c1, r1c2 = st.columns(2)
        with r1c1:
            section_header("🎯", "By Outcome", C["meetings"])
            if "meeting_outcome" in fm.columns:
                oc = fm["meeting_outcome"].value_counts().reset_index()
                oc.columns = ["Outcome", "Count"]
                fig = px.bar(oc, x="Outcome", y="Count", color_discrete_sequence=[C["meetings"]])
                fig.update_layout(xaxis_title="", yaxis_title="")
                st.plotly_chart(styled_fig(fig, 260), use_container_width=True)

        with r1c2:
            section_header("👤", "By Rep", C["meetings"])
            if "hubspot_owner_name" in fm.columns:
                br = fm["hubspot_owner_name"].value_counts().reset_index()
                br.columns = ["Rep", "Count"]
                fig = px.bar(br, x="Rep", y="Count", color_discrete_sequence=[C["meetings"]])
                fig.update_layout(xaxis_title="", yaxis_title="")
                st.plotly_chart(styled_fig(fig, 260), use_container_width=True)

        r2c1, r2c2 = st.columns(2)
        with r2c1:
            section_header("📂", "By Type", C["meetings"])
            if "call_and_meeting_type" in fm.columns:
                bt = fm["call_and_meeting_type"].value_counts().reset_index()
                bt.columns = ["Type", "Count"]
                fig = px.bar(bt, y="Type", x="Count", orientation="h", color_discrete_sequence=[C["emails"]])
                fig.update_layout(xaxis_title="", yaxis_title="")
                st.plotly_chart(styled_fig(fig, 260), use_container_width=True)

        with r2c2:
            section_header("🔗", "By Source", C["meetings"])
            if "meeting_source" in fm.columns:
                bs = fm["meeting_source"].value_counts().reset_index()
                bs.columns = ["Source", "Count"]
                fig = px.bar(bs, y="Source", x="Count", orientation="h", color_discrete_sequence=[C["gong"]])
                fig.update_layout(xaxis_title="", yaxis_title="")
                st.plotly_chart(styled_fig(fig, 260), use_container_width=True)

        section_divider()

        # Top 15 companies
        if "company_name" in fm.columns:
            section_header("🏢", "Top 15 Companies by Meeting Count", C["meetings"])
            top_co = fm["company_name"].value_counts().head(15).reset_index()
            top_co.columns = ["Company", "Meetings"]
            fig = px.bar(top_co, y="Company", x="Meetings", orientation="h",
                         color_discrete_sequence=[C["meetings"]])
            fig.update_layout(xaxis_title="", yaxis_title="", yaxis=dict(autorange="reversed"))
            st.plotly_chart(styled_fig(fig, 400), use_container_width=True)

        section_divider()

        # Detail table
        section_header("📋", "All Meetings", C["meetings"])
        mtg_cols = [c for c in ("meeting_start_time", "hubspot_owner_name", "company_name", "meeting_name",
                                 "meeting_outcome", "call_and_meeting_type", "meeting_source", "has_gong") if c in fm.columns]
        if mtg_cols:
            st.dataframe(_display_df(_safe_sort(fm[mtg_cols].copy(), mtg_cols[0])),
                         use_container_width=True, hide_index=True)


# ════════════════════════════════════════════════════════════════════════
# PAGE: ✅ TASKS
# ════════════════════════════════════════════════════════════════════════
elif st.session_state.page == "tasks":

    st.markdown("""<div class="page-header">
        <h1>✅ Tasks</h1>
        <p class="page-sub">The to-do list that keeps the engine running.</p>
    </div>""", unsafe_allow_html=True)

    if ft.empty:
        empty_state("No tasks in this range. Inbox zero? 🎉")
    else:
        n_tasks = len(ft)
        n_comp = 0
        n_overdue = 0
        if "task_status" in ft.columns:
            status = ft["task_status"].astype(str).str.upper().str.strip()
            n_comp = int(status.isin({"COMPLETED", "COMPLETE", "DONE"}).sum())
            if "due_date" in ft.columns:
                due = pd.to_datetime(ft["due_date"], errors="coerce")
                not_done = ~status.isin({"COMPLETED", "COMPLETE", "DONE"})
                past_due = due.notna() & (due < pd.Timestamp(date.today()))
                n_overdue = int((not_done & past_due).sum())

        comp_rate = f"{n_comp/n_tasks*100:.0f}%" if n_tasks > 0 else "—"

        kpi([
            ("Total Tasks", f"{n_tasks:,}", "amber"),
            ("Completed", f"{n_comp:,}", "green"),
            ("Completion Rate", comp_rate, "violet"),
            ("Overdue", f"{n_overdue:,}", "red" if n_overdue > 0 else ""),
        ])

        section_divider()

        ch1, ch2, ch3 = st.columns(3)
        with ch1:
            section_header("📊", "By Status", C["tasks"])
            if "task_status" in ft.columns:
                ts = ft["task_status"].value_counts().reset_index()
                ts.columns = ["Status", "Count"]
                fig = px.bar(ts, x="Status", y="Count", color_discrete_sequence=[C["tasks"]])
                fig.update_layout(xaxis_title="", yaxis_title="")
                st.plotly_chart(styled_fig(fig, 260), use_container_width=True)

        with ch2:
            section_header("🔺", "By Priority", C["tasks"])
            if "priority" in ft.columns:
                tp = ft["priority"].value_counts().reset_index()
                tp.columns = ["Priority", "Count"]
                fig = px.bar(tp, x="Priority", y="Count", color_discrete_sequence=[C["tasks"]])
                fig.update_layout(xaxis_title="", yaxis_title="")
                st.plotly_chart(styled_fig(fig, 260), use_container_width=True)

        with ch3:
            section_header("👤", "By Rep", C["tasks"])
            if "hubspot_owner_name" in ft.columns:
                tr = ft["hubspot_owner_name"].value_counts().reset_index()
                tr.columns = ["Rep", "Count"]
                fig = px.bar(tr, x="Rep", y="Count", color_discrete_sequence=[C["tasks"]])
                fig.update_layout(xaxis_title="", yaxis_title="")
                st.plotly_chart(styled_fig(fig, 260), use_container_width=True)

        section_divider()

        # Detail table
        section_header("📋", "All Tasks", C["tasks"])
        ft_disp = ft.copy()
        if "due_date" in ft_disp.columns and "task_status" in ft_disp.columns:
            due = pd.to_datetime(ft_disp["due_date"], errors="coerce")
            stat = ft_disp["task_status"].astype(str).str.upper().str.strip()
            not_done = ~stat.isin({"COMPLETED", "COMPLETE", "DONE"})
            past_due = due.notna() & (due < pd.Timestamp(date.today()))
            ft_disp["Overdue?"] = (not_done & past_due).map({True: "⚠️ Yes", False: ""})

        task_cols = [c for c in ("due_date", "hubspot_owner_name", "company_name", "task_title",
                                  "task_status", "priority", "task_type", "Overdue?") if c in ft_disp.columns]
        if task_cols:
            st.dataframe(_display_df(_safe_sort(ft_disp[task_cols].copy(), task_cols[0])),
                         use_container_width=True, hide_index=True)


# ════════════════════════════════════════════════════════════════════════
# PAGE: 🎫 TICKETS
# ════════════════════════════════════════════════════════════════════════
elif st.session_state.page == "tickets":

    st.markdown("""<div class="page-header">
        <h1>🎫 Tickets</h1>
        <p class="page-sub">Support issues, tracked and closed.</p>
    </div>""", unsafe_allow_html=True)

    if fk.empty:
        empty_state("No tickets in this range. Clean slate! ✨")
    else:
        n_tickets = len(fk)
        n_closed = 0
        if "ticket_status" in fk.columns:
            status_upper = fk["ticket_status"].astype(str).str.upper().str.strip()
            n_closed = int(status_upper.isin({"CLOSED", "RESOLVED", "DONE"}).sum())
        n_open = n_tickets - n_closed

        kpi([
            ("Total Created", f"{n_tickets:,}", "red"),
            ("Closed", f"{n_closed:,}", "green"),
            ("Open", f"{n_open:,}", "amber" if n_open > 0 else ""),
        ])

        section_divider()

        ch1, ch2 = st.columns(2)
        with ch1:
            section_header("📊", "Open vs Closed", C["tickets"])
            oc_data = pd.DataFrame({"Status": ["Open", "Closed"], "Count": [n_open, n_closed]})
            fig = px.pie(oc_data, names="Status", values="Count", hole=0.5,
                         color="Status", color_discrete_map={"Open": C["tasks"], "Closed": C["active"]})
            fig.update_traces(textinfo="label+value", textfont=dict(color="#ede9fc", size=12))
            st.plotly_chart(styled_fig(fig, 280), use_container_width=True)

        with ch2:
            section_header("📂", "By Status", C["tickets"])
            if "ticket_status" in fk.columns:
                ts = fk["ticket_status"].value_counts().reset_index()
                ts.columns = ["Status", "Count"]
                fig = px.bar(ts, x="Status", y="Count", color_discrete_sequence=[C["tickets"]])
                fig.update_layout(xaxis_title="", yaxis_title="")
                st.plotly_chart(styled_fig(fig, 280), use_container_width=True)

        section_divider()

        # Detail table
        section_header("📋", "All Tickets", C["tickets"])
        tkt_cols = [c for c in ("created_date", "hubspot_owner_name", "company_name", "ticket_name",
                                 "ticket_status", "pipeline", "deal_name", "ticket_category") if c in fk.columns]
        if tkt_cols:
            st.dataframe(_display_df(_safe_sort(fk[tkt_cols].copy(), tkt_cols[0])),
                         use_container_width=True, hide_index=True)


# ════════════════════════════════════════════════════════════════════════
# PAGE: 🏥 DEAL HEALTH (logic 100% preserved, restyled)
# ════════════════════════════════════════════════════════════════════════
elif st.session_state.page == "deals":

    st.markdown("""<div class="page-header">
        <h1>🏥 Deal Health</h1>
        <p class="page-sub">Pipeline pulse — who's engaged, who's going dark.</p>
    </div>""", unsafe_allow_html=True)

    deals_f = _frep(_fpipe(data.deals))
    active = deals_f[~deals_f["is_terminal"]].copy() if "is_terminal" in deals_f.columns else deals_f.copy()

    # For deal health: use ALL activity (not rep-filtered)
    all_meetings = data.meetings
    all_calls = data.calls
    all_tasks = data.tasks
    all_emails = data.emails
    all_notes = data.notes
    all_tickets = data.tickets

    an = _frep(data.notes)

    if active.empty:
        empty_state("No active deals found. Check your filters! 🔍")
    else:
        # ── Build per-deal activity by matching on BOTH company_name AND deal_name ──
        now = pd.Timestamp.now()
        d7, d30 = now - pd.Timedelta(days=7), now - pd.Timedelta(days=30)

        activity_sources = [
            (all_calls, "Call", "activity_date"),
            (all_meetings, "Meeting", "meeting_start_time"),
            (all_tasks, "Task", None),
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

            if typ == "Task":
                dt = pd.NaT
                for try_col in ("activity_date", "created_date", "due_date", "completed_at"):
                    if try_col in df.columns:
                        candidate = pd.to_datetime(df[try_col], errors="coerce")
                        if dt is pd.NaT:
                            dt = candidate
                        else:
                            dt = dt.fillna(candidate)
                t["_dt"] = dt if not isinstance(dt, type(pd.NaT)) else pd.NaT
            else:
                t["_dt"] = pd.to_datetime(df[dc], errors="coerce") if dc in df.columns else pd.NaT
            t["_tp"] = typ
            t["_is_rep"] = df["hubspot_owner_name"].isin(REPS_IN_SCOPE) if "hubspot_owner_name" in df.columns else False
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

        active["_co"] = active["company_name"].astype(str).str.strip().str.lower() if "company_name" in active.columns else ""
        active["_dn"] = active["deal_name"].astype(str).str.strip().str.lower() if "deal_name" in active.columns else ""

        deal_health_rows = []
        deal_activity_cache = {}

        for idx, deal in active.iterrows():
            co = deal["_co"]
            dn = deal["_dn"]

            if not all_act.empty:
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

            if not matched_act.empty:
                recent = matched_act[matched_act["_dt"] >= d30].sort_values("_dt", ascending=False).head(15)
                deal_activity_cache[dn] = recent

        mg = pd.DataFrame(deal_health_rows)

        # KPIs
        na = len(mg[mg["health"] == "Active"])
        nw = len(mg) - na
        matched_deals = mg[mg["total"] > 0]
        kpi([
            ("Active Deals", f"{len(mg):,}", "violet"),
            ("Pipeline", f"${mg['amount'].sum():,.0f}" if "amount" in mg.columns else "$0", "blue"),
            ("Engaged 7d", f"{na}", "green"),
            ("Needs Attention", f"{nw}", "red"),
            ("Company Match", f"{len(matched_deals)}/{len(mg)}", "cyan"),
        ])

        section_divider()

        # ── 📧 Email Pipeline Reports ──
        REP_EMAILS = {
            "Jake Lynch": "jlynch@calyxcontainers.com",
            "Owen Labombard": "olabombard@calyxcontainers.com",
            "Lance Mitton": "lmitton@calyxcontainers.com",
            "Dave Borkowski": "dborkowski@calyxcontainers.com",
            "Brad Sherman": "bsherman@calyxcontainers.com",
        }
        CC_EMAILS = ["xward@calyxcontainers.com", "kbissell@calyxcontainers.com"]

        def _health_color(h):
            return {"Active": "#34d399", "Stale": "#fbbf24", "Inactive": "#fb7185", "No Activity": "#6a6283"}.get(h, "#6a6283")

        def _health_label(h):
            return {"Active": "✅ Active", "Stale": "⚠️ Stale", "Inactive": "🔴 Inactive", "No Activity": "⚫ No Activity"}.get(h, h)

        def _hex_to_rgb(hex_color):
            """Convert #rrggbb to 'r,g,b' for rgba()."""
            h = hex_color.lstrip("#")
            return f"{int(h[0:2],16)},{int(h[2:4],16)},{int(h[4:6],16)}"

        def build_html_email(rep, rep_first, rd, ai_summary, ai_deal_analyses):
            """Build a stunning HTML email for a rep's pipeline report."""
            today_str = date.today().strftime("%B %d, %Y")
            total_val = rd["amount"].sum() if "amount" in rd.columns else 0
            n_deals = len(rd)
            n_active = len(rd[rd["health"] == "Active"])
            n_stale = len(rd[rd["health"] == "Stale"])
            n_inactive = len(rd[rd["health"].isin(["Inactive", "No Activity"])])

            # Sort deals: needs attention first, then active
            deal_order = {"Inactive": 0, "No Activity": 1, "Stale": 2, "Active": 3}
            rd_sorted = rd.copy()
            rd_sorted["_sort"] = rd_sorted["health"].map(deal_order).fillna(4)
            rd_sorted = rd_sorted.sort_values(["_sort", "amount"], ascending=[True, False])

            # Build deal cards HTML
            deal_cards_html = ""
            for _, d in rd_sorted.iterrows():
                dn = d.get("deal_name", "Unknown")
                co = d.get("company_name", "")
                stage = d.get("deal_stage", "")
                amt = d.get("amount", 0)
                health = d.get("health", "No Activity")
                days_idle = d.get("days_idle", None)
                a30 = d.get("a30", 0)
                hcolor = _health_color(health)
                hlabel = _health_label(health)
                idle_str = f"{int(days_idle)}d ago" if days_idle is not None else "—"
                forecast = d.get("forecast_category", "")

                # Get AI analysis for this deal
                dn_key = str(dn).strip().lower()
                deal_ai = ai_deal_analyses.get(dn_key, "")
                deal_ai_html = ""
                if deal_ai:
                    deal_ai_html = f'''
                    <tr><td colspan="4" style="padding:12px 16px 16px;border-top:1px solid #2d2750;">
                        <div style="background:#1a1530;border-radius:8px;padding:14px 16px;border-left:3px solid {hcolor};">
                            <div style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:1px;color:#9b93b7;margin-bottom:8px;">🤖 AI Insight</div>
                            <div style="font-size:13px;color:#c4bfdb;line-height:1.6;">{deal_ai}</div>
                        </div>
                    </td></tr>'''

                deal_cards_html += f'''
                <table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-bottom:12px;border-radius:12px;overflow:hidden;border:1px solid #2d2750;background:#151228;">
                    <tr>
                        <td colspan="4" style="height:3px;background:{hcolor};font-size:0;line-height:0;">&nbsp;</td>
                    </tr>
                    <tr>
                        <td colspan="3" style="padding:16px 16px 4px;">
                            <div style="font-size:15px;font-weight:700;color:#ede9fc;">{dn}</div>
                            <div style="font-size:12px;color:#9b93b7;margin-top:2px;">{co}</div>
                        </td>
                        <td style="padding:16px 16px 4px;text-align:right;vertical-align:top;">
                            <span style="display:inline-block;font-size:11px;font-weight:700;color:{hcolor};background:rgba({_hex_to_rgb(hcolor)},0.12);padding:3px 10px;border-radius:6px;">{hlabel}</span>
                        </td>
                    </tr>
                    <tr>
                        <td style="padding:8px 16px 14px;width:25%;">
                            <div style="font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:1px;color:#6a6283;">Amount</div>
                            <div style="font-size:16px;font-weight:800;color:#818cf8;margin-top:2px;">${amt:,.0f}</div>
                        </td>
                        <td style="padding:8px 16px 14px;width:25%;">
                            <div style="font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:1px;color:#6a6283;">Stage</div>
                            <div style="font-size:12px;font-weight:600;color:#c4bfdb;margin-top:4px;">{stage}</div>
                        </td>
                        <td style="padding:8px 16px 14px;width:25%;">
                            <div style="font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:1px;color:#6a6283;">Last Touch</div>
                            <div style="font-size:12px;font-weight:600;color:#c4bfdb;margin-top:4px;">{idle_str}</div>
                        </td>
                        <td style="padding:8px 16px 14px;width:25%;">
                            <div style="font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:1px;color:#6a6283;">30d Activity</div>
                            <div style="font-size:12px;font-weight:600;color:#c4bfdb;margin-top:4px;">{a30} touches</div>
                        </td>
                    </tr>
                    {deal_ai_html}
                </table>'''

            # Assemble full email
            html = f'''<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Pipeline Health Report</title></head>
<body style="margin:0;padding:0;background:#080614;font-family:'Segoe UI',Roboto,'Helvetica Neue',Arial,sans-serif;">

<!-- Preheader -->
<div style="display:none;max-height:0;overflow:hidden;font-size:1px;color:#080614;">
    {rep_first}, your pipeline report is ready — {n_deals} deals, ${total_val:,.0f} in play.
</div>

<!-- Outer wrapper -->
<table width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#080614;padding:20px 0;">
<tr><td align="center">

<!-- Main container -->
<table width="640" cellpadding="0" cellspacing="0" border="0" style="max-width:640px;width:100%;background:#0c0a1a;border-radius:16px;overflow:hidden;border:1px solid #1e1a35;">

    <!-- Header with gradient -->
    <tr><td style="background:linear-gradient(135deg,#1a1145 0%,#1e1535 50%,#1a1230 100%);padding:40px 32px 32px;">
        <table width="100%" cellpadding="0" cellspacing="0" border="0">
            <tr>
                <td>
                    <div style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:2.5px;color:#818cf8;margin-bottom:8px;">Calyx Activity Hub</div>
                    <div style="font-size:26px;font-weight:800;color:#ede9fc;line-height:1.2;">Pipeline Health Report</div>
                    <div style="font-size:13px;color:#9b93b7;margin-top:6px;">{today_str}</div>
                </td>
                <td width="80" style="text-align:right;vertical-align:top;">
                    <div style="width:56px;height:56px;border-radius:50%;background:linear-gradient(135deg,#818cf8,#c084fc,#f472b6);display:inline-block;text-align:center;line-height:56px;font-size:20px;font-weight:800;color:#0c0a1a;">{"".join([w[0] for w in rep.split()[:2]]).upper()}</div>
                </td>
            </tr>
        </table>
    </td></tr>

    <!-- Greeting -->
    <tr><td style="padding:28px 32px 0;">
        <div style="font-size:16px;color:#ede9fc;line-height:1.5;">Hey {rep_first} 👋</div>
        <div style="font-size:14px;color:#9b93b7;line-height:1.6;margin-top:8px;">Here's your weekly pipeline intelligence report. Every deal, every signal, every recommendation — all in one place.</div>
    </td></tr>

    <!-- Pipeline Snapshot KPIs -->
    <tr><td style="padding:24px 32px;">
        <table width="100%" cellpadding="0" cellspacing="0" border="0">
            <tr>
                <td width="25%" style="padding:0 4px 0 0;">
                    <div style="background:#151228;border:1px solid #2d2750;border-radius:12px;padding:16px;text-align:center;border-top:3px solid #a78bfa;">
                        <div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:1.2px;color:#9b93b7;">Deals</div>
                        <div style="font-size:24px;font-weight:800;color:#a78bfa;margin-top:4px;">{n_deals}</div>
                    </div>
                </td>
                <td width="25%" style="padding:0 4px;">
                    <div style="background:#151228;border:1px solid #2d2750;border-radius:12px;padding:16px;text-align:center;border-top:3px solid #818cf8;">
                        <div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:1.2px;color:#9b93b7;">Pipeline</div>
                        <div style="font-size:24px;font-weight:800;color:#818cf8;margin-top:4px;">${total_val:,.0f}</div>
                    </div>
                </td>
                <td width="25%" style="padding:0 4px;">
                    <div style="background:#151228;border:1px solid #2d2750;border-radius:12px;padding:16px;text-align:center;border-top:3px solid #34d399;">
                        <div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:1.2px;color:#9b93b7;">Active</div>
                        <div style="font-size:24px;font-weight:800;color:#34d399;margin-top:4px;">{n_active}</div>
                    </div>
                </td>
                <td width="25%" style="padding:0 0 0 4px;">
                    <div style="background:#151228;border:1px solid #2d2750;border-radius:12px;padding:16px;text-align:center;border-top:3px solid #fb7185;">
                        <div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:1.2px;color:#9b93b7;">Attention</div>
                        <div style="font-size:24px;font-weight:800;color:#fb7185;margin-top:4px;">{n_stale + n_inactive}</div>
                    </div>
                </td>
            </tr>
        </table>
    </td></tr>

    <!-- AI Executive Summary -->
    <tr><td style="padding:0 32px 24px;">
        <div style="background:linear-gradient(135deg,#1a1530 0%,#1e1535 100%);border:1px solid #2d2750;border-radius:12px;padding:24px;border-left:4px solid #c084fc;">
            <div style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:1.5px;color:#c084fc;margin-bottom:12px;">🧠 AI Pipeline Summary</div>
            <div style="font-size:14px;color:#c4bfdb;line-height:1.7;">{ai_summary}</div>
        </div>
    </td></tr>

    <!-- Section: Deal Cards -->
    <tr><td style="padding:0 32px 8px;">
        <table width="100%" cellpadding="0" cellspacing="0" border="0">
            <tr>
                <td style="height:1px;background:linear-gradient(90deg,transparent,#2d2750,transparent);"></td>
            </tr>
        </table>
        <div style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:2px;color:#9b93b7;margin:20px 0 16px;padding-left:2px;">📋 Deal-by-Deal Breakdown</div>
    </td></tr>

    <tr><td style="padding:0 32px 24px;">
        {deal_cards_html}
    </td></tr>

    <!-- Footer -->
    <tr><td style="padding:24px 32px 32px;border-top:1px solid #1e1a35;">
        <table width="100%" cellpadding="0" cellspacing="0" border="0">
            <tr>
                <td>
                    <div style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:2px;color:#818cf8;margin-bottom:4px;">Calyx Activity Hub</div>
                    <div style="font-size:11px;color:#6a6283;line-height:1.6;">Powered by AI · Generated {today_str}</div>
                    <div style="font-size:11px;color:#6a6283;margin-top:4px;">Questions? Reach out to Xander Ward or Kyle Bissell.</div>
                </td>
                <td style="text-align:right;vertical-align:bottom;">
                    <div style="font-size:20px;">📊</div>
                </td>
            </tr>
        </table>
    </td></tr>

</table>
<!-- End main container -->

</td></tr>
</table>
</body></html>'''
            return html

        section_header("📧", "Pipeline Health Reports", C["emails"])
        st.markdown("Generate AI-powered pipeline reports with deal-by-deal analysis and email them to each rep (CC: Xander & Kyle).", unsafe_allow_html=True)

        if st.button("📧  Generate & Email Pipeline Reports", key="email_reports", type="primary"):
            try:
                import anthropic
                import smtplib
                from email.mime.text import MIMEText
                from email.mime.multipart import MIMEMultipart

                client = anthropic.Anthropic(api_key=st.secrets["ANTHROPIC_API_KEY"])

                smtp_host = st.secrets.get("SMTP_HOST", "smtp.gmail.com")
                smtp_port = int(st.secrets.get("SMTP_PORT", 587))
                smtp_user = st.secrets.get("SMTP_USER", "")
                smtp_pass = st.secrets.get("SMTP_PASS", "")
                smtp_from = st.secrets.get("SMTP_FROM", smtp_user)

                progress_bar = st.progress(0, text="Starting pipeline analysis...")
                report_results = {}  # rep -> (ai_summary, ai_deal_analyses, rd)
                reps_to_report = [r for r in selected_reps if r in REP_EMAILS]
                total_reps = len(reps_to_report)

                for rep_idx, rep in enumerate(reps_to_report):
                    progress_bar.progress(
                        rep_idx / max(total_reps, 1),
                        text=f"Analyzing {rep}'s pipeline ({rep_idx + 1}/{total_reps})..."
                    )

                    rd = mg[mg["hubspot_owner_name"] == rep] if "hubspot_owner_name" in mg.columns else pd.DataFrame()
                    if rd.empty:
                        report_results[rep] = ("No active deals in pipeline.", {}, rd)
                        continue

                    # Build comprehensive pipeline context
                    pipeline_context = f"TODAY'S DATE: {date.today().strftime('%Y-%m-%d')} ({date.today().strftime('%A')})\n"
                    pipeline_context += f"REP: {rep}\n"
                    pipeline_context += f"TOTAL ACTIVE DEALS: {len(rd)}\n"
                    pipeline_context += f"TOTAL PIPELINE VALUE: ${rd['amount'].sum():,.0f}\n" if "amount" in rd.columns else ""
                    n_act_rep = len(rd[rd["health"] == "Active"])
                    n_att_rep = len(rd) - n_act_rep
                    pipeline_context += f"DEALS ACTIVE (7d): {n_act_rep} | NEEDS ATTENTION: {n_att_rep}\n\n"

                    deal_contexts = {}
                    for _, deal_row in rd.iterrows():
                        dn = str(deal_row.get("deal_name", "Unknown"))
                        dn_key = dn.strip().lower()
                        ctx = f"Deal: {dn}\n"
                        ctx += f"  Company: {deal_row.get('company_name', '')}\n"
                        ctx += f"  Stage: {deal_row.get('deal_stage', '')}\n"
                        ctx += f"  Forecast: {deal_row.get('forecast_category', '')}\n"
                        ctx += f"  Amount: ${deal_row.get('amount', 0):,.0f}\n"
                        ctx += f"  Close Date: {deal_row.get('close_date', '')}\n"
                        ctx += f"  Health: {deal_row.get('health', '')} | Days Idle: {deal_row.get('days_idle', 'N/A')}\n"
                        ctx += f"  Activity (30d): {deal_row.get('a30', 0)} | Total: {deal_row.get('total', 0)}\n"
                        ctx += f"  Breakdown: {deal_row.get('calls', 0)} calls, {deal_row.get('mtgs', 0)} mtgs, {deal_row.get('emails', 0)} emails, {deal_row.get('tasks', 0)} tasks\n"
                        cached = deal_activity_cache.get(dn_key)
                        if cached is not None and not cached.empty:
                            ctx += "  Recent Activity:\n"
                            for _, act in cached.head(8).iterrows():
                                dt_str = act["_dt"].strftime("%m/%d") if pd.notna(act["_dt"]) else "?"
                                ctx += f"    - {dt_str} | {act['_tp']} | {act['_owner']} | {act['_summary'][:100]}\n"
                        deal_contexts[dn_key] = ctx
                        pipeline_context += ctx + "\n"

                    # 1) Get executive summary for the whole pipeline
                    summary_resp = client.messages.create(
                        model="claude-sonnet-4-20250514",
                        max_tokens=600,
                        system="""You are a sharp, warm sales ops coach at Calyx Containers (cannabis packaging). Write a 3-4 sentence executive summary of this rep's pipeline health. Be specific about which deals look good, which need work, and one overarching pattern. Reference specific deal names. Keep it conversational and motivating. No markdown formatting — just clean prose.""",
                        messages=[{"role": "user", "content": pipeline_context}]
                    )
                    ai_summary = summary_resp.content[0].text

                    # 2) Get per-deal analyses in batch
                    deals_prompt = f"TODAY'S DATE: {date.today().strftime('%Y-%m-%d')} ({date.today().strftime('%A')})\n\n"
                    deals_prompt += "For EACH deal below, write a 2-sentence analysis: (1) what's happening and (2) one specific action for this week. Be concise and tactical.\n\n"
                    deals_prompt += "Format your response as:\nDEAL: [exact deal name]\nANALYSIS: [your 2 sentences]\n\n"
                    deals_prompt += "Here are the deals:\n\n"
                    for dn_key, ctx in deal_contexts.items():
                        deals_prompt += ctx + "\n---\n"

                    deals_resp = client.messages.create(
                        model="claude-sonnet-4-20250514",
                        max_tokens=2500,
                        system="""You are a sharp sales ops analyst at Calyx Containers. For each deal, write exactly 2 sentences: what's happening and one creative action for this week. Be specific about dates. No breakup emails or ultimatums — keep it warm and tactical. No markdown — plain text only.

Format each as:
DEAL: [exact deal name from the data]
ANALYSIS: [2 sentences]""",
                        messages=[{"role": "user", "content": deals_prompt}]
                    )

                    # Parse deal analyses
                    ai_deal_analyses = {}
                    raw_analyses = deals_resp.content[0].text
                    current_deal = None
                    current_analysis = []
                    for line in raw_analyses.split("\n"):
                        line_s = line.strip()
                        if line_s.upper().startswith("DEAL:"):
                            if current_deal and current_analysis:
                                ai_deal_analyses[current_deal] = " ".join(current_analysis).strip()
                            deal_name_raw = line_s[5:].strip()
                            current_deal = deal_name_raw.lower().strip()
                            current_analysis = []
                        elif line_s.upper().startswith("ANALYSIS:"):
                            current_analysis.append(line_s[9:].strip())
                        elif line_s and current_deal:
                            current_analysis.append(line_s)
                    if current_deal and current_analysis:
                        ai_deal_analyses[current_deal] = " ".join(current_analysis).strip()

                    report_results[rep] = (ai_summary, ai_deal_analyses, rd)

                # Send emails
                progress_bar.progress(0.85, text="Building beautiful emails...")
                emails_sent = 0
                email_errors = []
                html_previews = {}

                for rep, (ai_summary, ai_deal_analyses, rd) in report_results.items():
                    if rep not in REP_EMAILS:
                        continue
                    rep_first = rep.split()[0]

                    if rd.empty:
                        continue

                    html_body = build_html_email(rep, rep_first, rd, ai_summary, ai_deal_analyses)
                    html_previews[rep] = html_body

                    if smtp_user and smtp_pass:
                        try:
                            msg = MIMEMultipart("alternative")
                            msg["Subject"] = f"📊 Your Pipeline Intelligence Report — {date.today().strftime('%b %d')}"
                            msg["From"] = smtp_from
                            msg["To"] = REP_EMAILS[rep]
                            msg["Cc"] = ", ".join(CC_EMAILS)

                            # Plain text fallback
                            plain = f"Hi {rep_first},\n\nYour pipeline health report is ready.\n\n"
                            plain += f"Pipeline Summary:\n{ai_summary}\n\n"
                            plain += f"View the full HTML version in your email client.\n\n"
                            plain += "— Calyx Activity Hub AI\n"

                            msg.attach(MIMEText(plain, "plain"))
                            msg.attach(MIMEText(html_body, "html"))

                            if "smtp_server" not in st.session_state:
                                server = smtplib.SMTP(smtp_host, smtp_port)
                                server.starttls()
                                server.login(smtp_user, smtp_pass)
                                st.session_state["smtp_server"] = server

                            recipients = [REP_EMAILS[rep]] + CC_EMAILS
                            st.session_state["smtp_server"].sendmail(smtp_from, recipients, msg.as_string())
                            emails_sent += 1
                        except Exception as e:
                            email_errors.append(f"{rep}: {e}")
                            # Reset server on error
                            st.session_state.pop("smtp_server", None)

                # Cleanup SMTP
                if "smtp_server" in st.session_state:
                    try:
                        st.session_state["smtp_server"].quit()
                    except:
                        pass
                    st.session_state.pop("smtp_server", None)

                progress_bar.progress(1.0, text="✅ Done!")

                # Show results
                if emails_sent > 0:
                    st.success(f"✅ Sent {emails_sent} pipeline reports!")
                elif not smtp_user:
                    st.info("📋 Reports generated below — add SMTP_USER, SMTP_PASS, SMTP_HOST to secrets to enable email.")
                if email_errors:
                    for err in email_errors:
                        st.warning(f"⚠️ {err}")

                # Show HTML previews in-app
                for rep, html_body in html_previews.items():
                    with st.expander(f"📧 {rep}'s Report Preview", expanded=False):
                        ai_summary = report_results[rep][0]
                        st.markdown(f"**AI Summary:** {ai_summary}")
                        st.markdown("---")
                        st.components.v1.html(html_body, height=800, scrolling=True)

            except Exception as e:
                st.error(f"Report generation failed: {e}")

        section_divider()

        # Health + Flagged
        h1, h2 = st.columns([1, 2])
        with h1:
            section_header("💊", "Health Distribution", C["active"])
            hc = mg["health"].value_counts().reset_index()
            hc.columns = ["Health", "Count"]
            fh = px.pie(hc, names="Health", values="Count", color="Health", hole=0.5,
                        color_discrete_map={"Active": C["active"], "Stale": C["stale"],
                                            "Inactive": C["inactive"], "No Activity": C["none"]})
            styled_fig(fh, 300)
            fh.update_traces(textinfo="label+value", textfont=dict(color="#ede9fc", size=11),
                             marker=dict(line=dict(color="#0c0a1a", width=2)))
            st.plotly_chart(fh, use_container_width=True)

        with h2:
            section_header("🚩", "Flagged — Forecast with No Recent Activity", C["overdue"])
            if "forecast_category" in mg.columns:
                fl = mg[(mg["forecast_category"].isin({"Best Case", "Commit", "Expect"})) &
                        (mg["health"].isin(["Stale", "Inactive", "No Activity"]))]
            else: fl = pd.DataFrame()
            if not fl.empty:
                sc = [c for c in ("hubspot_owner_name", "deal_name", "company_name", "deal_stage",
                                  "forecast_category", "amount", "close_date", "health", "days_idle", "a30") if c in fl.columns]
                st.dataframe(_safe_sort(fl[sc], "days_idle"), use_container_width=True, hide_index=True,
                             column_config={
                                 "amount": st.column_config.NumberColumn("Amount", format="$%,.0f"),
                                 "days_idle": st.column_config.NumberColumn("Days Idle"),
                             })
            else:
                st.success("✅ All forecasted deals have recent activity.")

        section_divider()

        # Per-rep deals
        section_header("👥", "Deals by Rep", C["score"])
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
                for didx, (_, deal_row) in enumerate(rd.iterrows()):
                    dn_key = str(deal_row.get("deal_name", "")).strip().lower()
                    cached = deal_activity_cache.get(dn_key)
                    if cached is not None and not cached.empty:
                        with st.expander(f"📋 {deal_row.get('deal_name', 'Unknown')} — Activity Timeline"):
                            timeline = cached[["_dt", "_tp", "_owner", "_summary"]].copy()
                            timeline.columns = ["Date", "Type", "By", "Summary"]
                            timeline["Date"] = pd.to_datetime(timeline["Date"], errors="coerce").dt.strftime("%Y-%m-%d")
                            timeline["Summary"] = timeline["Summary"].str[:120]
                            st.dataframe(timeline, use_container_width=True, hide_index=True)

                            btn_key = f"ai_{rep}_{didx}_{dn_key[:30]}"
                            if st.button("🤖 Analyze Deal Health", key=btn_key):
                                with st.spinner("Analyzing..."):
                                    deal_info = f"TODAY'S DATE: {date.today().strftime('%Y-%m-%d')} ({date.today().strftime('%A')})\n\n"
                                    deal_info += f"Deal: {deal_row.get('deal_name', '')}\n"
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
                                            max_tokens=600,
                                            system="""You are a sharp sales ops analyst at Calyx Containers, a cannabis packaging company (concentrate jars, drams, tubes, boxes, flexpack, labels). You analyze deal activity and give actionable, creative recommendations.

When you see patterns of failed outreach (unanswered emails, left voicemails, no-shows, ghosting), don't just say "follow up again." Instead suggest creative re-engagement tactics like:
- Sending a relevant industry article, market data, or regulatory update that affects their business
- Reaching out to a different contact at the company (procurement, operations, marketing)
- Engaging via a different channel (LinkedIn, text, drop-in visit, send samples)
- Creating urgency with lead time warnings, minimum order changes, or pricing shifts
- Referencing a competitor win or industry trend relevant to their product line
- Having a senior leader (Kyle Bissell, VP Sales) reach out directly
- Offering a value-add like a packaging audit, compliance review, or cost comparison
- Connecting them with an existing customer reference in a similar market
- Sending physical samples of new products or updated packaging options

Be direct, specific, and brief. No fluff. Use the activity data to identify the real pattern and prescribe the right medicine.

IMPORTANT: Today's date is provided at the top of the deal info. Pay close attention to HOW RECENT each activity is — "yesterday" and "2 weeks ago" tell very different stories. Reference specific dates and timeframes in your analysis (e.g., "the meeting yesterday" not "a recent meeting").

IMPORTANT: Do NOT recommend breakup emails, ultimatums, or threatening to walk away. These are real relationships — keep the tone warm and persistent. A quiet deal doesn't mean a dead deal. Focus on adding value and finding creative new angles to re-engage.""",
                                            messages=[{"role": "user", "content": f"""Analyze this deal:

1. **Momentum** (1 sentence): Accelerating, stalling, or dead?
2. **Pattern** (1 sentence): What does the activity tell us? (one-way outreach, mutual engagement, going dark, etc.)
3. **Risk** (1 sentence): Biggest threat to closing?
4. **Action** (2-3 sentences): What should the rep do THIS WEEK? Be creative and tactical.

{deal_info}"""}]
                                        )
                                        st.markdown(response.content[0].text)
                                    except Exception as e:
                                        st.warning(f"AI analysis unavailable: {e}")

        section_divider()

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
