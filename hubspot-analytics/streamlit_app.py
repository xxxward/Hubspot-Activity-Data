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
from zoneinfo import ZoneInfo
from src.utils.logging import setup_logging
from src.parsing.filters import REPS_IN_SCOPE, PIPELINES_IN_SCOPE
from src.metrics.scoring import WEIGHTS
from main import load_all, AnalyticsData

# Close Status options for filtering
CLOSE_STATUS_OPTIONS = ["Best Case", "Expect", "Opportunity"]

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
.health-badge.cold { background: rgba(106, 98, 131, 0.15); color: var(--text-muted); }
.health-badge.fire { background: rgba(52, 211, 153, 0.15); color: var(--green); }

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

# ── Timezone ───────────────────────────────────────────────────────────
LOCAL_TZ = ZoneInfo("America/Denver")  # Mountain Time

def _localize_dt_col(series):
    """Convert a datetime Series to Mountain Time for display.
    
    Google Sheets data typically has naive timestamps that are already in local time.
    We localize them as Mountain Time directly (not as UTC).
    If they're already tz-aware, we convert.
    """
    dt = pd.to_datetime(series, errors="coerce")
    if dt.empty:
        return dt
    try:
        if dt.dt.tz is None:
            # Naive timestamps from Google Sheets — treat as already Mountain Time
            dt = dt.dt.tz_localize(LOCAL_TZ, ambiguous="NaT", nonexistent="NaT")
        else:
            dt = dt.dt.tz_convert(LOCAL_TZ)
        return dt
    except Exception:
        return dt


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
    ("notes",   "📝", "Notes"),
    ("tickets", "🎫", "Tickets"),
    ("deals",   "🏥", "Deal Health"),
]

# Count badges
_counts = {
    "command": None,
    "calls": len(data.calls) if not data.calls.empty else 0,
    "meetings": len(data.meetings) if not data.meetings.empty else 0,
    "tasks": len(data.tasks) if not data.tasks.empty else 0,
    "notes": len(data.notes) if not data.notes.empty else 0,
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
    today = datetime.now(LOCAL_TZ).date()
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

    fc1, fc2, fc3, fc4 = st.columns([2, 2, 2, 1])
    with fc1:
        selected_reps = st.multiselect("👤 Sales Reps", REPS_IN_SCOPE, default=REPS_IN_SCOPE)
    with fc2:
        if st.session_state.page == "deals":
            selected_pipelines = st.multiselect("🔀 Pipelines", PIPELINES_IN_SCOPE, default=PIPELINES_IN_SCOPE)
        else:
            selected_pipelines = PIPELINES_IN_SCOPE
    with fc3:
        if st.session_state.page == "deals":
            selected_close_status = st.multiselect("📊 Close Status", CLOSE_STATUS_OPTIONS, default=CLOSE_STATUS_OPTIONS)
        else:
            selected_close_status = CLOSE_STATUS_OPTIONS
    with fc4:
        st.markdown("<br>", unsafe_allow_html=True)
        is_filtered = (len(selected_reps) < len(REPS_IN_SCOPE)) or (len(selected_pipelines) < len(PIPELINES_IN_SCOPE)) or (len(selected_close_status) < len(CLOSE_STATUS_OPTIONS)) or quick != "7d"
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

def _fclose_status(df):
    if df.empty or "close_status" not in df.columns: return df
    return df[df["close_status"].isin(selected_close_status)].copy()

def _fdate_raw(df, date_col="activity_date"):
    if df.empty: return df
    for col in (date_col, "activity_date", "meeting_start_time", "created_date"):
        if col in df.columns:
            dt = pd.to_datetime(df[col], errors="coerce")
            # Strip timezone if present to keep comparisons simple
            if dt.dt.tz is not None:
                dt = dt.dt.tz_localize(None)
            start_ts = pd.Timestamp(start_date)
            end_ts = pd.Timestamp(end_date) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
            mask = dt.notna() & (dt >= start_ts) & (dt <= end_ts)
            return df[mask].copy()
    return df

def _fdate(df, col="period_day"):
    if df.empty or col not in df.columns: return df
    dt = pd.to_datetime(df[col], errors="coerce")
    end_ts = pd.Timestamp(end_date) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
    return df[(dt >= pd.Timestamp(start_date)) & (dt <= end_ts)].copy()

def _safe_sort(df, col, asc=False):
    try: return df.sort_values(col, ascending=asc)
    except: return df

def _display_df(df):
    """Clean a DataFrame for st.dataframe — fix mixed types and localize to Mountain Time."""
    df = df.copy()
    for col in df.columns:
        if df[col].dtype == object:
            has_ts = df[col].apply(lambda x: isinstance(x, pd.Timestamp)).any()
            if has_ts:
                localized = _localize_dt_col(df[col])
                df[col] = localized.dt.strftime("%Y-%m-%d %H:%M").fillna("")
        elif pd.api.types.is_datetime64_any_dtype(df[col]):
            localized = _localize_dt_col(df[col])
            df[col] = localized.dt.strftime("%Y-%m-%d %H:%M").fillna("")
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

def _safe_num(val, default=0):
    """Safely convert a value to a number, returning default if NaN/None."""
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return default
    try:
        return val if not pd.isna(val) else default
    except (TypeError, ValueError):
        return default

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
            if candidate.dt.tz is not None:
                candidate = candidate.dt.tz_localize(None)
            task_dt = task_dt.fillna(candidate)
    start_ts = pd.Timestamp(start_date)
    end_ts = pd.Timestamp(end_date) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
    ft = ft_all[task_dt.notna() & (task_dt >= start_ts) & (task_dt <= end_ts)].copy()
else:
    ft = ft_all

total_activities = len(fm) + len(fc) + len(ft) + len(fe) + len(fn) + len(fk)

# ── Data Diagnostics (toggle in sidebar) ──
with st.sidebar.expander("🔧 Debug: Date Diagnostics"):
    st.caption(f"Filter: {start_date} → {end_date}")
    for label, src_df, dt_col in [
        ("Meetings (raw)", data.meetings, "meeting_start_time"),
        ("Calls (raw)", data.calls, "activity_date"),
        ("Emails (raw)", data.emails, "activity_date"),
        ("Notes (raw)", data.notes, "activity_date"),
        ("Tickets (raw)", data.tickets, "created_date"),
        ("Tasks (raw)", data.tasks, "activity_date"),
    ]:
        if not src_df.empty and dt_col in src_df.columns:
            dts = pd.to_datetime(src_df[dt_col], errors="coerce").dropna()
            if not dts.empty:
                st.markdown(f"**{label}**: {len(dts)} rows, tz={dts.dt.tz}, min={dts.min()}, max={dts.max()}")
                # Count how many fall in today
                dts_naive = dts.dt.tz_localize(None) if dts.dt.tz is not None else dts
                today_mask = (dts_naive >= pd.Timestamp(date.today())) & (dts_naive < pd.Timestamp(date.today()) + pd.Timedelta(days=1))
                st.markdown(f"  → Today: {today_mask.sum()}")
            else:
                st.markdown(f"**{label}**: all NaT")
        elif not src_df.empty:
            st.markdown(f"**{label}**: no `{dt_col}` column. Cols: {list(src_df.columns)[:8]}")
        else:
            st.markdown(f"**{label}**: empty")


# ════════════════════════════════════════════════════════════════════════
# GAMIFIED SCORING ENGINE
# ════════════════════════════════════════════════════════════════════════

# ── Role Profiles ──
REP_ROLES = {
    "Owen Labombard": "sdr",
    "Lance Mitton": "acquisition",
    "Brad Sherman": "acquisition",
    "Jake Lynch": "am",
    "Dave Borkowski": "am",
    "Alex Gonzalez": "ceo",
}

ROLE_LABELS = {
    "sdr": "🎯 SDR",
    "acquisition": "🚀 Acquisition",
    "am": "💼 Account Manager",
    "ceo": "👑 CEO",
}

# ── Per-Rep Coaching Profiles ──
REP_COACHING = {
    "Owen Labombard": {
        "tone": "encouraging_supportive",
        "voice": """COACHING TONE FOR OWEN: Owen is a newer SDR who's still building confidence. Be encouraging and supportive. Celebrate what he's doing right before suggesting improvements. Use phrases like "nice work on...", "you're building good momentum with...", "one thing that could level this up...". Frame suggestions as growth opportunities, not corrections. He needs to feel like he's winning and learning, not failing.""",
    },
    "Lance Mitton": {
        "tone": "challenging_direct",
        "voice": """COACHING TONE FOR LANCE: Lance responds to being challenged. He's competitive and wants to be pushed. Be direct — "this deal is slipping and here's why", "you're leaving money on the table", "the activity says you've gone quiet — what's the play?". Don't sugarcoat. Use competitive framing like "deals like this close when reps do X" or "top performers would..." He'll respect bluntness and tune out fluff.""",
    },
    "Brad Sherman": {
        "tone": "no_bs_concise",
        "voice": """COACHING TONE FOR BRAD: Brad is a no-BS northeast personality. He'll view this as a waste of time if it doesn't immediately help him. Be EXTREMELY concise — 2 sentences max per deal. No motivational language, no filler, no "great job" unless it's genuinely warranted. Just: what's happening, what to do. If you can say it in 5 words, don't use 10. He respects efficiency above all else.""",
    },
    "Jake Lynch": {
        "tone": "collaborative_strategic",
        "voice": """COACHING TONE FOR JAKE: Jake is a senior AM — treat him as a peer, not a direct report. Use collaborative language: "what if we tried...", "one angle worth exploring...", "thinking about this together...". He's strategic and wants to understand the WHY behind the recommendation. Connect the dots between activity patterns and business outcomes. Respect his experience — frame suggestions as options, not instructions.""",
    },
    "Dave Borkowski": {
        "tone": "direct_accountability",
        "voice": """COACHING TONE FOR DAVE: Dave responds best to direct, candid accountability. Don't sugarcoat, don't plant seeds — come down hard. He respects it and takes action when called out specifically. Use phrases like "I'm not seeing follow-up on...", "this is unacceptable given what you committed to...", "you told Kyle you'd prioritize proactive follow-ups and increased call activity — the data says otherwise." Reference specific deals and specific gaps. Dave committed to: (1) proactive follow-ups after every meeting, (2) increased call activity, (3) clearer tracking to prevent gaps, (4) staying ahead of key accounts and maintaining stronger momentum. Hold him to EVERY ONE of these commitments. If he's falling short, say so directly. He will appreciate the candor and act on it.""",
    },
    "Alex Gonzalez": {
        "tone": "executive_brief",
        "voice": """COACHING TONE FOR ALEX: Alex is the CEO. Keep it extremely brief and high-level. He doesn't need tactical advice — just flag what needs his attention and why. One sentence per deal max.""",
    },
}

def _get_coaching_profile(rep_name):
    """Get the coaching voice instructions for a specific rep."""
    profile = REP_COACHING.get(rep_name, {})
    return profile.get("voice", "Be direct, specific, and helpful. One clear insight, one clear action.")

def _get_role_context(rep_name):
    """Get role-aware context string for the AI."""
    role = REP_ROLES.get(rep_name, "acquisition")
    role_contexts = {
        "sdr": "This rep is an SDR — their job is outbound prospecting and booking meetings. Calls are their bread and butter, but the REAL win is converting outreach into face-to-face meetings. Coach accordingly.",
        "acquisition": "This rep is on the Acquisition team — they're hunting new business with lower-value deals ($1K-$10K) and quicker sales cycles. Speed and volume matter. They should be moving deals fast, not nursing them for months.",
        "am": "This rep is a senior Account Manager handling existing relationships and growth deals. These are higher-value, longer-cycle deals ($10K-$100K+). Relationships and strategic engagement matter more than volume. Every touch should be intentional.",
        "ceo": "This is the CEO — their deals often bypass normal HubSpot pipelines and go straight to NetSuite. Activity in HubSpot won't reflect their full engagement. Keep coaching minimal and high-level.",
    }
    return role_contexts.get(role, "")

def _ai_call(client, model, max_tokens, system, messages, retries=3):
    """Make an AI API call with retry on rate limit errors."""
    import time
    for attempt in range(retries):
        try:
            return client.messages.create(
                model=model, max_tokens=max_tokens,
                system=system, messages=messages
            )
        except Exception as e:
            if "rate_limit" in str(e).lower() and attempt < retries - 1:
                wait = 30 * (attempt + 1)
                st.toast(f"⏳ Rate limit hit — waiting {wait}s... (attempt {attempt + 2}/{retries})")
                time.sleep(wait)
            else:
                raise

# Model selection: use Haiku for large reports to stay within rate limits
AI_MODEL_FAST = "claude-haiku-4-5-20251001"   # For heavy multi-deal reports
AI_MODEL_SMART = "claude-sonnet-4-20250514"    # For single-deal coaching

# ── Role-Based Activity Weights ──
ROLE_WEIGHTS = {
    "sdr": {
        "meetings": 8, "calls": 1, "emails": 0.5,
        "completed_tasks": 2, "overdue_tasks": -3, "tickets": 1, "notes": 0.5,
    },
    "acquisition": {
        "meetings": 6, "calls": 3, "emails": 1,
        "completed_tasks": 3, "overdue_tasks": -5, "tickets": 2, "notes": 1,
    },
    "am": {
        "meetings": 10, "calls": 4, "emails": 1.5,
        "completed_tasks": 3, "overdue_tasks": -5, "tickets": 3, "notes": 1.5,
    },
    "ceo": {
        "meetings": 5, "calls": 2, "emails": 1,
        "completed_tasks": 1, "overdue_tasks": -1, "tickets": 1, "notes": 0.5,
    },
}

# ── Score Thresholds (per role) ──
SCORE_THRESHOLDS = {
    "sdr":         {"fire": 200, "solid": 100, "push": 50},
    "acquisition": {"fire": 120, "solid": 60,  "push": 30},
    "am":          {"fire": 100, "solid": 50,  "push": 25},
    "ceo":         {"fire": 50,  "solid": 20,  "push": 10},
}

SCORE_LEVELS = {
    "fire":  ("🔥 On Fire", "fire"),
    "solid": ("✅ Solid", "active"),
    "push":  ("⚡ Needs Push", "declining"),
    "cold":  ("🧊 Cold", "cold"),
}

# ── Deal-Linked Activity Tier Multipliers ──
# Activities tied to a company with an active deal get 1.5x
# Activities with a company but no active deal get 1.0x
# Activities with no company association get 0.5x

def _get_active_deal_companies():
    """Get set of company names (lowered) that have active deals."""
    deals_all = data.deals
    if deals_all.empty or "company_name" not in deals_all.columns:
        return set()
    active_mask = ~deals_all["is_terminal"] if "is_terminal" in deals_all.columns else pd.Series(True, index=deals_all.index)
    return set(deals_all[active_mask]["company_name"].astype(str).str.strip().str.lower()) - {"", "nan"}

_deal_companies = _get_active_deal_companies()

def _deal_tier_multiplier(activity_df):
    """Calculate the deal-tier weighted count for an activity DataFrame.
    Returns a float: sum of multiplied activities."""
    if activity_df.empty or "company_name" not in activity_df.columns:
        return len(activity_df) * 0.5  # no company info = unlinked
    companies = activity_df["company_name"].astype(str).str.strip().str.lower()
    has_company = (companies != "") & (companies != "nan")
    has_deal = companies.isin(_deal_companies)
    # Deal-linked: 1.5x, Company but no deal: 1.0x, Unlinked: 0.5x
    score = (has_deal * 1.5) + (has_company & ~has_deal) * 1.0 + (~has_company) * 0.5
    return float(score.sum())

def _calc_streak(rep_name):
    """Calculate consecutive active days streak for a rep (looking backward from today)."""
    daily = data.activity_counts_daily
    if daily.empty or "hubspot_owner_name" not in daily.columns or "period_day" not in daily.columns:
        return 0
    rep_daily = daily[daily["hubspot_owner_name"] == rep_name].copy()
    if rep_daily.empty:
        return 0
    rep_daily["period_day"] = pd.to_datetime(rep_daily["period_day"], errors="coerce")
    rep_daily = rep_daily.dropna(subset=["period_day"])
    if rep_daily.empty:
        return 0
    # Sum activity columns per day
    act_cols = [c for c in ("meetings", "calls", "emails", "completed_tasks") if c in rep_daily.columns]
    if not act_cols:
        return 0
    rep_daily["_total"] = rep_daily[act_cols].sum(axis=1)
    active_days = set(rep_daily[rep_daily["_total"] > 0]["period_day"].dt.date)
    # Count consecutive days backward from today
    streak = 0
    check_date = date.today()
    while check_date in active_days:
        streak += 1
        check_date -= timedelta(days=1)
    return streak

def _calc_wow_growth(rep_name):
    """Calculate week-over-week activity growth. Returns a float multiplier (e.g., 1.15 for 15% growth)."""
    daily = data.activity_counts_daily
    if daily.empty or "hubspot_owner_name" not in daily.columns or "period_day" not in daily.columns:
        return 1.0
    rep_daily = daily[daily["hubspot_owner_name"] == rep_name].copy()
    if rep_daily.empty:
        return 1.0
    rep_daily["period_day"] = pd.to_datetime(rep_daily["period_day"], errors="coerce")
    rep_daily = rep_daily.dropna(subset=["period_day"])
    act_cols = [c for c in ("meetings", "calls", "emails", "completed_tasks") if c in rep_daily.columns]
    if not act_cols:
        return 1.0
    rep_daily["_total"] = rep_daily[act_cols].sum(axis=1)
    today_ts = pd.Timestamp(date.today())
    this_week = rep_daily[(rep_daily["period_day"] >= today_ts - pd.Timedelta(days=7)) & (rep_daily["period_day"] <= today_ts)]
    last_week = rep_daily[(rep_daily["period_day"] >= today_ts - pd.Timedelta(days=14)) & (rep_daily["period_day"] < today_ts - pd.Timedelta(days=7))]
    tw_total = this_week["_total"].sum()
    lw_total = last_week["_total"].sum()
    if lw_total == 0:
        return 1.15 if tw_total > 0 else 1.0  # growing from zero
    return tw_total / lw_total

def build_leaderboard():
    rows = []
    for rep in selected_reps:
        role = REP_ROLES.get(rep, "acquisition")
        weights = ROLE_WEIGHTS[role]

        # Get per-rep filtered DataFrames
        rm = fm[fm["hubspot_owner_name"] == rep] if not fm.empty and "hubspot_owner_name" in fm.columns else pd.DataFrame()
        rc = fc[fc["hubspot_owner_name"] == rep] if not fc.empty and "hubspot_owner_name" in fc.columns else pd.DataFrame()
        re_ = fe[fe["hubspot_owner_name"] == rep] if not fe.empty and "hubspot_owner_name" in fe.columns else pd.DataFrame()
        rn = fn[fn["hubspot_owner_name"] == rep] if not fn.empty and "hubspot_owner_name" in fn.columns else pd.DataFrame()
        rk = fk[fk["hubspot_owner_name"] == rep] if not fk.empty and "hubspot_owner_name" in fk.columns else pd.DataFrame()

        m = len(rm)
        c = len(rc)
        e = len(re_)
        n = len(rn)
        k = len(rk)

        # Deal-tier weighted counts
        m_w = _deal_tier_multiplier(rm) if not rm.empty else 0
        c_w = _deal_tier_multiplier(rc) if not rc.empty else 0
        e_w = _deal_tier_multiplier(re_) if not re_.empty else 0
        n_w = _deal_tier_multiplier(rn) if not rn.empty else 0
        k_w = _deal_tier_multiplier(rk) if not rk.empty else 0

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

        # Base score (role-weighted × deal-tier)
        base_score = (
            m_w * weights["meetings"] +
            c_w * weights["calls"] +
            e_w * weights["emails"] +
            comp * weights["completed_tasks"] +
            over * weights["overdue_tasks"] +
            k_w * weights["tickets"] +
            n_w * weights["notes"]
        )

        # Streak bonus: +10% if 5+ consecutive active days
        streak = _calc_streak(rep)
        streak_bonus = 1.10 if streak >= 5 else 1.0

        # Week-over-week growth bonus: +15% if this week > last week
        wow = _calc_wow_growth(rep)
        wow_bonus = 1.15 if wow > 1.0 else 1.0

        final_score = base_score * streak_bonus * wow_bonus

        # Determine level
        thresholds = SCORE_THRESHOLDS.get(role, SCORE_THRESHOLDS["acquisition"])
        if final_score >= thresholds["fire"]:
            level = "fire"
        elif final_score >= thresholds["solid"]:
            level = "solid"
        elif final_score >= thresholds["push"]:
            level = "push"
        else:
            level = "cold"

        rows.append({
            "Rep": rep, "Role": role, "Meetings": m, "Calls": c, "Emails": e,
            "Tasks": comp, "Overdue": over, "Notes": n, "Tickets": k,
            "Base Score": round(base_score, 1), "Streak": streak,
            "WoW": f"{'▲' if wow > 1 else '▼' if wow < 1 else '—'} {abs(wow - 1) * 100:.0f}%",
            "Streak 🔥": f"{'🔥 ' if streak >= 5 else ''}{streak}d",
            "Score": round(final_score, 1),
            "Level": level,
            "_wow_raw": wow,
        })

    # CEO always unranked — sort others by score, then append CEO at end
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    ceo_mask = df["Role"] == "ceo"
    ranked = df[~ceo_mask].sort_values("Score", ascending=False).reset_index(drop=True)
    unranked = df[ceo_mask]
    return pd.concat([ranked, unranked], ignore_index=True)

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
        ("Notes", f"{len(fn):,}", "violet"),
        ("Tickets", f"{len(fk):,}", "red"),
    ])

    section_divider()

    # ── Row 2: Leaderboard + Activity Mix ──
    col_lb, col_mix = st.columns([3, 2])

    with col_lb:
        section_header("🏆", "Team Leaderboard", C["score"])
        if not lb.empty:
            lb_display = lb.copy()
            # Rank: CEO gets 👑, others get medals/numbers
            ranks = []
            rank_icons = {0: "🥇", 1: "🥈", 2: "🥉"}
            rank_num = 0
            for _, row in lb_display.iterrows():
                if row["Role"] == "ceo":
                    ranks.append("👑")
                else:
                    ranks.append(rank_icons.get(rank_num, f"#{rank_num + 1}"))
                    rank_num += 1
            lb_display.insert(0, "Rank", ranks)
            # Level badges
            lb_display["Level "] = lb_display["Level"].map(lambda x: SCORE_LEVELS.get(x, ("", ""))[0])
            # Role labels
            lb_display["Role "] = lb_display["Role"].map(ROLE_LABELS)

            show_cols = ["Rank", "Rep", "Role ", "Meetings", "Calls", "Emails", "Tasks",
                         "Overdue", "Streak 🔥", "WoW", "Score", "Level "]
            show_cols = [c for c in show_cols if c in lb_display.columns]
            st.dataframe(lb_display[show_cols], use_container_width=True, hide_index=True,
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

    # ── Row 3: Activity Trend ──
    if quick == "Today":
        # Hourly activity breakdown for today
        section_header("📈", "Today's Activity by Hour", C["calls"])

        # Build hourly data from all filtered activity sources
        hourly_frames = []
        for label, df_src, dt_col in [
            ("Meetings", fm, "meeting_start_time"),
            ("Calls", fc, "activity_date"),
            ("Emails", fe, "activity_date"),
            ("Tasks", ft, "activity_date"),
        ]:
            if df_src.empty:
                continue
            for try_col in (dt_col, "activity_date", "meeting_start_time", "created_date"):
                if try_col in df_src.columns:
                    dts = pd.to_datetime(df_src[try_col], errors="coerce").dropna()
                    if not dts.empty:
                        hours = dts.dt.hour
                        hc = hours.value_counts().reset_index()
                        hc.columns = ["Hour", "Count"]
                        hc["Type"] = label
                        hourly_frames.append(hc)
                    break

        if hourly_frames:
            hourly = pd.concat(hourly_frames, ignore_index=True)
            # Ensure all hours 0-23 exist for smooth chart
            all_hours = pd.DataFrame({"Hour": range(24)})
            types = hourly["Type"].unique()
            full_grid = pd.MultiIndex.from_product([range(24), types], names=["Hour", "Type"])
            full_df = pd.DataFrame(index=full_grid).reset_index()
            hourly = full_df.merge(hourly, on=["Hour", "Type"], how="left").fillna(0)
            hourly["Count"] = hourly["Count"].astype(int)
            # Format hour labels
            hourly["Time"] = hourly["Hour"].apply(lambda h: f"{h % 12 or 12}{'am' if h < 12 else 'pm'}")

            fig_hourly = px.bar(
                hourly, x="Hour", y="Count", color="Type",
                color_discrete_map={
                    "Meetings": C["meetings"], "Calls": C["calls"],
                    "Emails": C["emails"], "Tasks": C["tasks"],
                },
                barmode="stack",
            )
            fig_hourly.update_layout(
                xaxis=dict(
                    tickmode="array",
                    tickvals=list(range(0, 24, 2)),
                    ticktext=[f"{h % 12 or 12}{'am' if h < 12 else 'pm'}" for h in range(0, 24, 2)],
                    title="",
                ),
                yaxis_title="",
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5),
            )
            st.plotly_chart(styled_fig(fig_hourly, 300), use_container_width=True)
        else:
            empty_state("No activity logged yet today. Still early! ☕")
    else:
        # Standard daily trend
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
        rep_colors = {"sdr": "#67e8f9", "acquisition": "#fbbf24", "am": "#818cf8", "ceo": "#c084fc"}
        cols = st.columns(min(3, len(lb)))
        for i, (_, r) in enumerate(lb.iterrows()):
            rep = r["Rep"]
            role = r["Role"]
            initials = "".join([w[0] for w in rep.split()[:2]]).upper()
            color = rep_colors.get(role, "#a78bfa")
            total_rep = r["Meetings"] + r["Calls"] + r["Emails"] + r["Tasks"] + r["Notes"] + r["Tickets"]
            level_text, level_cls = SCORE_LEVELS.get(r["Level"], ("", ""))
            role_label = ROLE_LABELS.get(role, "")
            streak = r.get("Streak", 0)
            wow_raw = r.get("_wow_raw", 1.0)

            # Streak flame indicator
            streak_html = ""
            if streak >= 5:
                streak_html = f'<span style="font-size:0.68rem;color:#fbbf24;margin-left:6px;">🔥 {streak}d streak!</span>'
            elif streak >= 3:
                streak_html = f'<span style="font-size:0.68rem;color:#9b93b7;margin-left:6px;">⚡ {streak}d streak</span>'

            # WoW indicator
            wow_html = ""
            if wow_raw > 1.0:
                wow_pct = (wow_raw - 1) * 100
                wow_html = f'<span style="font-size:0.68rem;color:#34d399;margin-left:6px;">▲ {wow_pct:.0f}% vs last week</span>'
            elif wow_raw < 1.0:
                wow_pct = (1 - wow_raw) * 100
                wow_html = f'<span style="font-size:0.68rem;color:#fb7185;margin-left:6px;">▼ {wow_pct:.0f}% vs last week</span>'

            # CEO gets special treatment
            if role == "ceo":
                level_cls = "active"
                level_text = "👑 CEO"

            # Score bar fill (percentage of fire threshold)
            thresholds = SCORE_THRESHOLDS.get(role, SCORE_THRESHOLDS["acquisition"])
            fill_pct = min(100, (r["Score"] / max(thresholds["fire"], 1)) * 100)
            bar_color = {"fire": "#34d399", "solid": "#818cf8", "push": "#fbbf24", "cold": "#fb7185"}.get(r["Level"], "#6a6283")

            with cols[i % len(cols)]:
                st.markdown(f"""<div class="rep-card">
                    <div style="display:flex;align-items:center;gap:12px;margin-bottom:10px;">
                        <div class="rep-avatar" style="background:{color};">{initials}</div>
                        <div>
                            <div class="rep-name" style="margin-bottom:0;">{rep}</div>
                            <div style="font-size:0.65rem;color:#6a6283;font-weight:600;text-transform:uppercase;letter-spacing:1px;">{role_label}</div>
                        </div>
                    </div>
                    <div class="rep-stats">
                        {r['Meetings']} mtgs · {r['Calls']} calls · {r['Emails']} emails<br>
                        {r['Tasks']} tasks · {r['Overdue']} overdue · {total_rep} total
                    </div>
                    <div style="display:flex;align-items:baseline;gap:8px;margin-top:10px;">
                        <div class="rep-score">{r['Score']}</div>
                        <span style="font-size:0.72rem;color:#6a6283;">pts</span>
                    </div>
                    <div style="background:#0c0a1a;border-radius:4px;height:6px;margin:8px 0;overflow:hidden;">
                        <div style="background:{bar_color};height:100%;width:{fill_pct}%;border-radius:4px;transition:width 0.3s ease;"></div>
                    </div>
                    <div style="display:flex;align-items:center;flex-wrap:wrap;gap:4px;">
                        <div class="health-badge {level_cls}">{level_text}</div>
                        {streak_html}{wow_html}
                    </div>
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
# PAGE: 📝 NOTES
# ════════════════════════════════════════════════════════════════════════
elif st.session_state.page == "notes":

    st.markdown("""<div class="page-header">
        <h1>📝 Notes</h1>
        <p class="page-sub">The paper trail that keeps deals moving.</p>
    </div>""", unsafe_allow_html=True)

    if fn.empty:
        empty_state("No notes in this range. Time to document! 📝")
    else:
        n_notes = len(fn)
        n_reps_noting = fn["hubspot_owner_name"].nunique() if "hubspot_owner_name" in fn.columns else 0
        n_companies = fn["company_name"].nunique() if "company_name" in fn.columns else 0
        n_deal_linked = len(fn[fn["deal_name"].astype(str).str.strip() != ""]) if "deal_name" in fn.columns else 0

        kpi([
            ("Total Notes", f"{n_notes:,}", "violet"),
            ("Reps Active", f"{n_reps_noting}", "blue"),
            ("Companies", f"{n_companies:,}", "pink"),
            ("Deal-Linked", f"{n_deal_linked:,}", "green"),
        ])

        section_divider()

        ch1, ch2 = st.columns(2)
        with ch1:
            section_header("👤", "Notes by Rep", C["notes"])
            if "hubspot_owner_name" in fn.columns:
                nr = fn["hubspot_owner_name"].value_counts().reset_index()
                nr.columns = ["Rep", "Count"]
                fig = px.bar(nr, x="Rep", y="Count", color_discrete_sequence=[C["notes"]])
                fig.update_layout(xaxis_title="", yaxis_title="")
                st.plotly_chart(styled_fig(fig, 280), use_container_width=True)

        with ch2:
            section_header("🏢", "Top Companies by Notes", C["notes"])
            if "company_name" in fn.columns:
                nc = fn["company_name"].value_counts().head(10).reset_index()
                nc.columns = ["Company", "Count"]
                fig = px.bar(nc, y="Company", x="Count", orientation="h",
                             color_discrete_sequence=[C["score"]])
                fig.update_layout(xaxis_title="", yaxis_title="")
                st.plotly_chart(styled_fig(fig, 280), use_container_width=True)

        section_divider()

        # Detail table
        section_header("📋", "All Notes", C["notes"])
        note_cols = [c for c in ("activity_date", "hubspot_owner_name", "company_name",
                                  "deal_name", "note_body") if c in fn.columns]
        if note_cols:
            fn_display = fn[note_cols].copy()
            # Truncate note body for display
            if "note_body" in fn_display.columns:
                fn_display["note_body"] = fn_display["note_body"].astype(str).str.replace(r'<[^>]+>', '', regex=True).str[:200]
            st.dataframe(_display_df(_safe_sort(fn_display, note_cols[0])),
                         use_container_width=True, hide_index=True)


# ════════════════════════════════════════════════════════════════════════
# PAGE: 🏥 DEAL HEALTH (logic 100% preserved, restyled)
# ════════════════════════════════════════════════════════════════════════
elif st.session_state.page == "deals":

    st.markdown("""<div class="page-header">
        <h1>🏥 Deal Health</h1>
        <p class="page-sub">Pipeline pulse — who's engaged, who's going dark.</p>
    </div>""", unsafe_allow_html=True)

    # Apply rep and pipeline filters to all data
    deals_base = _frep(_fpipe(data.deals))
    active_all = deals_base[~deals_base["is_terminal"]].copy() if "is_terminal" in deals_base.columns else deals_base.copy()
    
    # Apply close status filter only for detailed analysis and AI
    deals_f = _fclose_status(deals_base)
    active_filtered = deals_f[~deals_f["is_terminal"]].copy() if "is_terminal" in deals_f.columns else deals_f.copy()

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

        active_all["_co"] = active_all["company_name"].astype(str).str.strip().str.lower() if "company_name" in active_all.columns else ""
        active_all["_dn"] = active_all["deal_name"].astype(str).str.strip().str.lower() if "deal_name" in active_all.columns else ""

        deal_health_rows = []
        deal_activity_cache = {}

        for idx, deal in active_all.iterrows():
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

        # KPIs - use all deals regardless of close status filter
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

        # Create filtered version for detailed analysis that respects close status filter
        if len(selected_close_status) < len(CLOSE_STATUS_OPTIONS):
            # Only filter if not all close status options are selected
            mg_filtered = mg[mg["close_status"].isin(selected_close_status)] if "close_status" in mg.columns else mg.copy()
            st.info(f"🔍 **Close Status Filter Active:** Detailed views below show only {', '.join(selected_close_status)} deals. KPIs above show all deals.")
        else:
            mg_filtered = mg.copy()  # No filtering if all options selected

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
                amt = _safe_num(d.get("amount", 0))
                health = d.get("health", "No Activity")
                days_idle = d.get("days_idle", None)
                a30 = _safe_num(d.get("a30", 0))
                hcolor = _health_color(health)
                hlabel = _health_label(health)
                idle_str = f"{int(days_idle)}d ago" if days_idle is not None and not (isinstance(days_idle, float) and np.isnan(days_idle)) else "—"
                forecast = d.get("close_status", "")

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
                    pipeline_context += f"CLOSE STATUS FILTER: {', '.join(selected_close_status)}\n"
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
                        ctx += f"  Forecast: {deal_row.get('close_status', '')}\n"
                        ctx += f"  Amount: ${_safe_num(deal_row.get('amount', 0)):,.0f}\n"
                        ctx += f"  Close Date: {deal_row.get('close_date', '')}\n"
                        ctx += f"  Health: {deal_row.get('health', '')} | Days Idle: {_safe_num(deal_row.get('days_idle', 0), 'N/A')}\n"
                        ctx += f"  Activity (30d): {_safe_num(deal_row.get('a30', 0))} | Total: {_safe_num(deal_row.get('total', 0))}\n"
                        ctx += f"  Breakdown: {_safe_num(deal_row.get('calls', 0))} calls, {_safe_num(deal_row.get('mtgs', 0))} mtgs, {_safe_num(deal_row.get('emails', 0))} emails, {_safe_num(deal_row.get('tasks', 0))} tasks\n"
                        cached = deal_activity_cache.get(dn_key)
                        if cached is not None and not cached.empty:
                            ctx += "  Recent Activity:\n"
                            for _, act in cached.head(8).iterrows():
                                dt_str = act["_dt"].strftime("%m/%d") if pd.notna(act["_dt"]) else "?"
                                ctx += f"    - {dt_str} | {act['_tp']} | {act['_owner']} | {act['_summary'][:100]}\n"
                        deal_contexts[dn_key] = ctx
                        pipeline_context += ctx + "\n"

                    # 1) Get executive summary for the whole pipeline
                    coaching_voice = _get_coaching_profile(rep)
                    role_context = _get_role_context(rep)

                    summary_resp = _ai_call(client,
                        model=AI_MODEL_FAST,
                        max_tokens=600,
                        system=f"""You are a seasoned sales coach at Calyx Containers (cannabis packaging) writing a personalized pipeline overview for a specific rep. This goes in an email — it should feel like a quick coaching huddle, not a report card.

{coaching_voice}

{role_context}

CRITICAL: You are analyzing deals filtered by Close Status. Here's what each status means:
- "Expect" = High confidence (80-90% chance) - These are deals that should close this quarter
- "Best Case" = Moderate confidence (40-60% chance) - Stretch opportunities that could close with focused effort  
- "Opportunity" = Highest confidence (90%+ chance) - Deals that are essentially locked in

Currently analyzing deals with Close Status: {', '.join(selected_close_status)}

Focus your analysis on these confidence levels. If analyzing "Expect" deals, emphasize execution and removing barriers. If analyzing "Best Case" deals, focus on what needs to happen to increase confidence. If analyzing "Opportunity" deals, focus on protection and ensuring smooth close. Mix accordingly based on what's selected.

Write 3-4 sentences summarizing this rep's pipeline health. Be specific — mention deal names, call out what's working and what needs attention. Adapt your tone to this specific rep's coaching profile above. No markdown formatting — just clean, conversational prose.""",
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

                    deals_resp = _ai_call(client,
                        model=AI_MODEL_FAST,
                        max_tokens=2500,
                        system=f"""You are a seasoned sales coach at Calyx Containers giving deal-by-deal coaching notes for a specific rep. Each note goes inside a deal card in a beautiful HTML email.

{coaching_voice}

{role_context}

CLOSE STATUS INTELLIGENCE: You're analyzing deals by their Close Status confidence level:
- "Expect" (80-90% confidence) → Focus on execution: removing barriers, confirming next steps, ensuring smooth close process
- "Best Case" (40-60% confidence) → Focus on advancement: what specific actions can move this to "Expect" level? What objections/concerns need addressing?
- "Opportunity" (90%+ confidence) → Focus on protection: ensure nothing derails this, timing coordination, paperwork readiness

Currently filtering for: {', '.join(selected_close_status)}

Tailor your coaching to the confidence level. High confidence deals need execution focus, medium confidence deals need advancement tactics.

For each deal, write 1-2 sentences in the coaching style above. Include:
- What's really happening (read the activity direction — who's reaching out, who's responding?)
- One specific action, adapted to the deal size and close date urgency
- Be specific about dates ("since Feb 3" not "recently")
- Never recommend breakup emails or ultimatums

No markdown — plain text only. Keep it tight.

Format each as:
DEAL: [exact deal name from the data]
ANALYSIS: [your coaching note]""",
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

        # ── 📊 Sales Leadership Report ──
        LEADERSHIP_EMAILS = {
            "Xander Ward": "xward@calyxcontainers.com",
            "Kyle Bissell": "kbissell@calyxcontainers.com",
            "Alex Gonzalez": "alex@calyxcontainers.com",
        }

        LEADERSHIP_PROFILES = {
            "Xander Ward": {
                "role": "Rev Ops",
                "manages": "all reps (data & systems)",
                "voice": """You're reporting to the Rev Ops lead who built this entire analytics system. He thinks in systems, patterns, and process gaps. Give him the operational view — where are the bottlenecks, what's broken in the pipeline, which reps need support vs accountability. He wants to know what to FIX, not just what's wrong. He'll use this to guide Kyle and Alex's coaching conversations.""",
                "coaching_guide": "",  # Xander coaches the system, not the reps directly
            },
            "Kyle Bissell": {
                "role": "CRO / VP Sales",
                "manages": "Jake Lynch and Dave Borkowski (AM/Growth team)",
                "voice": """You're reporting to the CRO who directly manages the AM team (Jake and Dave). He cares about revenue outcomes, deal velocity, and whether his AMs are doing the right things on the right deals. Give him the revenue story — what's at risk, what's about to close, where does he need to step in personally. He's strategic and action-oriented.""",
                "coaching_guide": """
COACHING PLAYBOOK FOR KYLE — HOW TO GUIDE YOUR TEAM:

For Jake Lynch (Senior AM — collaborative, strategic thinker):
- Jake is a peer-level thinker. Don't tell him what to do — think WITH him.
- In your 1:1, try: "I was looking at the [deal name] data and had a thought — what if we..."
- Jake responds to strategic framing. Connect the dots between his deals and the bigger revenue picture.
- If he's stuck on a deal, offer to co-strategize or make a joint call. He values partnership.
- When Jake's deals are healthy, acknowledge it — "your engagement on [deal] is exactly the model."

For Dave Borkowski (AM — needs direct accountability, responds to being called out):
- Dave responds best to candid, specific feedback. Don't soften it — he respects directness and takes action.
- Dave committed to Kyle on Feb 9 that he would: prioritize proactive follow-ups, increase call activity, track more clearly, and stay ahead of key accounts. HOLD HIM TO THESE COMMITMENTS.
- In your 1:1, be specific: "Dave, you committed to proactive follow-ups after every meeting. I'm seeing [X deal] with no follow-up since [date]. What happened?"
- Call out the pattern, not just the instance: "I'm seeing 4 emails and no calls again. We talked about this."
- When he's executing well, acknowledge it — but don't let up. "Good follow-up on [deal]. Now let's make sure [other deal] gets the same treatment."
- Dave takes ownership when confronted directly. He'll say "you're right, I'll address it tomorrow" — your job is to check that he actually did.
""",
            },
            "Alex Gonzalez": {
                "role": "CEO",
                "manages": "Lance Mitton and Brad Sherman (Acquisition team), Owen Labombard (SDR)",
                "voice": """You're reporting to the CEO who's spearheading the acquisition team. He wants the 30,000-foot view of the acquisition pipeline plus any deals where his personal relationships could move the needle. He also needs to know how to coach each of his direct reports effectively.""",
                "coaching_guide": """
COACHING PLAYBOOK FOR ALEX — HOW TO GUIDE YOUR TEAM:

For Lance Mitton (Acquisition — competitive, responds to being challenged):
- Lance wants to be pushed. He'll tune out soft feedback.
- In your check-in, try: "Lance, the [deal] has been stale for X days — what's your plan to break through?"
- Use competitive framing: "I've seen reps close deals like this by doing Y — think you can beat that?"
- If Lance is crushing it, make sure he knows: "This is exactly the kind of hustle that moves the number."
- Don't sugarcoat. He respects directness and loses respect for softness.

For Brad Sherman (Acquisition — no-BS, needs efficiency):
- Brad is a northeast, no-nonsense operator. He'll view coaching as a waste of time if it's not immediately useful.
- Keep your feedback to ONE thing. Literally one sentence: "On [deal], try [specific action] this week."
- Don't explain the why unless he asks. He trusts the recommendation if it's sharp.
- In your check-in, don't do a deal-by-deal review — just flag the 1-2 deals that need his focus and move on.
- Brad is self-sufficient. Your job is to unblock him, not manage him.

For Owen Labombard (SDR — newer, needs confidence):
- Owen is still building his sales muscles. He needs encouragement MORE than correction.
- In your check-in, always start with what he did right: "Owen, I saw you booked X meetings this week — that's solid."
- When coaching, frame it as growth: "One thing that could level up your game..." not "You're not doing X."
- Celebrate his wins publicly when you can — it builds confidence fast.
- If his numbers are low, focus on technique, not effort. He's trying hard — help him work smarter.
""",
            },
        }

        section_divider()
        
        # ═══════════════════════════════════════════════════════════════════════════════
        # DAILY & WEEKLY ACTIVITY REPORTS
        # ═══════════════════════════════════════════════════════════════════════════════
        
        def _build_daily_activity_context(rep_name, target_date=None):
            """Build focused daily activity context for AI analysis."""
            if target_date is None:
                target_date = date.today()
            
            # Get date ranges
            today = pd.Timestamp(target_date)
            week_start = today - pd.Timedelta(days=6)  # 7-day window including today
            prev_week_start = week_start - pd.Timedelta(days=7)
            prev_week_end = week_start - pd.Timedelta(days=1)
            
            # Filter data for this rep
            rep_meetings = data.meetings[data.meetings["hubspot_owner_name"] == rep_name] if "hubspot_owner_name" in data.meetings.columns else pd.DataFrame()
            rep_calls = data.calls[data.calls["hubspot_owner_name"] == rep_name] if "hubspot_owner_name" in data.calls.columns else pd.DataFrame()
            rep_emails = data.emails[data.emails["hubspot_owner_name"] == rep_name] if "hubspot_owner_name" in data.emails.columns else pd.DataFrame()
            rep_tasks = data.tasks[data.tasks["hubspot_owner_name"] == rep_name] if "hubspot_owner_name" in data.tasks.columns else pd.DataFrame()
            rep_deals = data.deals[data.deals["hubspot_owner_name"] == rep_name] if "hubspot_owner_name" in data.deals.columns else pd.DataFrame()
            
            def _filter_by_date(df, date_col, start_date, end_date):
                if df.empty or date_col not in df.columns:
                    return df
                dt = pd.to_datetime(df[date_col], errors="coerce")
                if dt.dt.tz is not None:
                    dt = dt.dt.tz_localize(None)
                return df[(dt >= pd.Timestamp(start_date)) & (dt <= pd.Timestamp(end_date) + pd.Timedelta(days=1))]
            
            # Today's activity
            today_meetings = _filter_by_date(rep_meetings, "meeting_start_time", today, today)
            today_calls = _filter_by_date(rep_calls, "activity_date", today, today)
            today_emails = _filter_by_date(rep_emails, "activity_date", today, today)
            today_tasks = _filter_by_date(rep_tasks, "created_date", today, today)
            
            # This week's activity
            week_meetings = _filter_by_date(rep_meetings, "meeting_start_time", week_start, today)
            week_calls = _filter_by_date(rep_calls, "activity_date", week_start, today)
            week_emails = _filter_by_date(rep_emails, "activity_date", week_start, today)
            week_tasks = _filter_by_date(rep_tasks, "created_date", week_start, today)
            
            # Previous week's activity
            prev_meetings = _filter_by_date(rep_meetings, "meeting_start_time", prev_week_start, prev_week_end)
            prev_calls = _filter_by_date(rep_calls, "activity_date", prev_week_start, prev_week_end)
            prev_emails = _filter_by_date(rep_emails, "activity_date", prev_week_start, prev_week_end)
            prev_tasks = _filter_by_date(rep_tasks, "created_date", prev_week_start, prev_week_end)
            
            # Active deals (touched in last 14 days)
            two_weeks_ago = today - pd.Timedelta(days=14)
            recent_activity = pd.concat([
                _filter_by_date(rep_meetings, "meeting_start_time", two_weeks_ago, today),
                _filter_by_date(rep_calls, "activity_date", two_weeks_ago, today),
                _filter_by_date(rep_emails, "activity_date", two_weeks_ago, today)
            ], ignore_index=True)
            
            active_companies = set()
            if not recent_activity.empty and "company_name" in recent_activity.columns:
                active_companies = set(recent_activity["company_name"].dropna().str.strip().str.lower()) - {"", "nan"}
            
            active_deals = rep_deals[rep_deals["company_name"].str.strip().str.lower().isin(active_companies)] if "company_name" in rep_deals.columns else pd.DataFrame()
            active_deals = active_deals[~active_deals["is_terminal"]] if "is_terminal" in active_deals.columns else active_deals
            
            # Build context
            context = f"DAILY ACTIVITY REPORT\\n"
            context += f"Date: {target_date.strftime('%Y-%m-%d')} ({target_date.strftime('%A')})\\n"
            context += f"Rep: {rep_name}\\n\\n"
            
            # Today's numbers
            context += f"TODAY'S ACTIVITY:\\n"
            context += f"  Calls: {len(today_calls)}\\n"
            context += f"  Meetings: {len(today_meetings)}\\n"
            context += f"  Emails: {len(today_emails)}\\n"
            context += f"  Tasks: {len(today_tasks)}\\n\\n"
            
            # This week vs previous week
            context += f"WEEK COMPARISON (7-day rolling):\\n"
            context += f"  This Week: {len(week_calls)} calls, {len(week_meetings)} mtgs, {len(week_emails)} emails, {len(week_tasks)} tasks\\n"
            context += f"  Previous Week: {len(prev_calls)} calls, {len(prev_meetings)} mtgs, {len(prev_emails)} emails, {len(prev_tasks)} tasks\\n\\n"
            
            # Active deals context
            context += f"ACTIVE DEALS IN PLAY: {len(active_deals)}\\n"
            if not active_deals.empty:
                for _, deal in active_deals.head(8).iterrows():  # Limit to top 8 deals
                    context += f"  • {deal.get('deal_name', 'Unknown')} ({deal.get('company_name', '')}) - "
                    context += f"${_safe_num(deal.get('amount', 0)):,.0f} - {deal.get('deal_stage', '')} - {deal.get('close_status', '')}\\n"
            
            return context
        
        def _build_weekly_activity_context(rep_name, week_ending_date=None):
            """Build comprehensive weekly activity context for AI analysis."""
            if week_ending_date is None:
                week_ending_date = date.today()
            
            week_end = pd.Timestamp(week_ending_date)
            week_start = week_end - pd.Timedelta(days=6)
            prev_week_start = week_start - pd.Timedelta(days=7)
            prev_week_end = week_start - pd.Timedelta(days=1)
            month_start = week_end - pd.Timedelta(days=29)  # 30-day window
            
            # Filter data for this rep
            rep_meetings = data.meetings[data.meetings["hubspot_owner_name"] == rep_name] if "hubspot_owner_name" in data.meetings.columns else pd.DataFrame()
            rep_calls = data.calls[data.calls["hubspot_owner_name"] == rep_name] if "hubspot_owner_name" in data.calls.columns else pd.DataFrame()
            rep_emails = data.emails[data.emails["hubspot_owner_name"] == rep_name] if "hubspot_owner_name" in data.emails.columns else pd.DataFrame()
            rep_tasks = data.tasks[data.tasks["hubspot_owner_name"] == rep_name] if "hubspot_owner_name" in data.tasks.columns else pd.DataFrame()
            rep_deals = data.deals[data.deals["hubspot_owner_name"] == rep_name] if "hubspot_owner_name" in data.deals.columns else pd.DataFrame()
            
            def _filter_by_date(df, date_col, start_date, end_date):
                if df.empty or date_col not in df.columns:
                    return df
                dt = pd.to_datetime(df[date_col], errors="coerce")
                if dt.dt.tz is not None:
                    dt = dt.dt.tz_localize(None)
                return df[(dt >= pd.Timestamp(start_date)) & (dt <= pd.Timestamp(end_date) + pd.Timedelta(days=1))]
            
            # This week, previous week, and monthly averages
            week_meetings = _filter_by_date(rep_meetings, "meeting_start_time", week_start, week_end)
            week_calls = _filter_by_date(rep_calls, "activity_date", week_start, week_end)
            week_emails = _filter_by_date(rep_emails, "activity_date", week_start, week_end)
            week_tasks = _filter_by_date(rep_tasks, "created_date", week_start, week_end)
            
            prev_meetings = _filter_by_date(rep_meetings, "meeting_start_time", prev_week_start, prev_week_end)
            prev_calls = _filter_by_date(rep_calls, "activity_date", prev_week_start, prev_week_end)
            prev_emails = _filter_by_date(rep_emails, "activity_date", prev_week_start, prev_week_end)
            prev_tasks = _filter_by_date(rep_tasks, "created_date", prev_week_start, prev_week_end)
            
            month_meetings = _filter_by_date(rep_meetings, "meeting_start_time", month_start, week_end)
            month_calls = _filter_by_date(rep_calls, "activity_date", month_start, week_end)
            month_emails = _filter_by_date(rep_emails, "activity_date", month_start, week_end)
            month_tasks = _filter_by_date(rep_tasks, "created_date", month_start, week_end)
            
            # Deal progression analysis
            week_deal_activity = pd.concat([
                _filter_by_date(rep_meetings, "meeting_start_time", week_start, week_end),
                _filter_by_date(rep_calls, "activity_date", week_start, week_end),
                _filter_by_date(rep_emails, "activity_date", week_start, week_end)
            ], ignore_index=True)
            
            active_companies = set()
            if not week_deal_activity.empty and "company_name" in week_deal_activity.columns:
                active_companies = set(week_deal_activity["company_name"].dropna().str.strip().str.lower()) - {"", "nan"}
            
            # Build context
            context = f"WEEKLY ACTIVITY REPORT\\n"
            context += f"Week Ending: {week_ending_date.strftime('%Y-%m-%d')} ({week_ending_date.strftime('%A')})\\n"
            context += f"Rep: {rep_name}\\n\\n"
            
            # Activity breakdown
            context += f"ACTIVITY BREAKDOWN:\\n"
            context += f"  This Week: {len(week_calls)} calls, {len(week_meetings)} mtgs, {len(week_emails)} emails, {len(week_tasks)} tasks\\n"
            context += f"  Previous Week: {len(prev_calls)} calls, {len(prev_meetings)} mtgs, {len(prev_emails)} emails, {len(prev_tasks)} tasks\\n"
            context += f"  Monthly Avg: {len(month_calls)//4:.1f} calls, {len(month_meetings)//4:.1f} mtgs, {len(month_emails)//4:.1f} emails, {len(month_tasks)//4:.1f} tasks\\n\\n"
            
            # Deal activity this week
            context += f"DEALS ENGAGED THIS WEEK: {len(active_companies)}\\n"
            if active_companies:
                context += f"  Companies: {', '.join(list(active_companies)[:8])}{'...' if len(active_companies) > 8 else ''}\\n"
            
            return context
        
        # Daily Activity Reports
        section_header("📅", "Daily Activity Reports", C["calls"])
        st.markdown("Generate focused daily activity snapshots with weekly context and pattern recognition. Sent at end of each day.", unsafe_allow_html=True)
        
        dc1, dc2 = st.columns([3, 1])
        with dc1:
            selected_rep_daily = st.selectbox("👤 Select Rep for Daily Report", REPS_IN_SCOPE + ["Test with Owen's Data"], key="daily_rep")
        with dc2:
            report_date = st.date_input("📅 Report Date", date.today(), key="daily_date")
        
        if st.button("📅  Generate Daily Activity Report", key="daily_report", type="primary"):
            try:
                import anthropic
                import smtplib
                from email.mime.text import MIMEText
                from email.mime.multipart import MIMEMultipart
                
                client = anthropic.Anthropic(api_key=st.secrets["ANTHROPIC_API_KEY"])
                
                # Use test email for now, but get the right rep's data
                test_email = "xander@calyxcontainers.com"  # Your email for testing
                if selected_rep_daily == "Test with Owen's Data":
                    actual_rep = "Owen Labombard"  # Use Owen's activity data
                    display_name = "Owen Labombard (Test Mode)"
                else:
                    actual_rep = selected_rep_daily
                    display_name = actual_rep
                
                with st.spinner(f"Generating daily report for {display_name}..."):
                    
                    # Build activity context
                    daily_context = _build_daily_activity_context(actual_rep, report_date)
                    
                    # Get coaching voice for this rep
                    coaching_voice = _get_coaching_profile(actual_rep)
                    
                    # Generate AI report
                    daily_resp = _ai_call(client,
                        model=AI_MODEL_FAST,
                        max_tokens=500,
                        system=f"""You are an advanced AI sales coach from the future, communicating with a sales rep at Calyx Containers (cannabis packaging). Write like a sophisticated AI that's genuinely excited to help optimize their performance.

{coaching_voice}

IMPORTANT: Start with this futuristic AI introduction:
"Hey! I'm your AI sales coach, and I've been analyzing your activity patterns. Think of me as your data-powered wingman who never sleeps. I'm still learning your style, so if my insights feel off, just know I'm calibrating to your unique approach. This daily check-in is just the beginning - I'm building toward becoming your full sales intelligence system."

Then continue with your analysis:

TONE: Confident AI assistant from the future. Enthusiastic but not cheesy. Use data-driven language that sounds intelligent and forward-thinking.

FORMAT:
- Futuristic AI introduction (3-4 sentences as noted above)
- Today's performance analysis (what the data shows about their day)
- Pattern detection (what trends I'm spotting in their approach)  
- Tomorrow's optimization (data-driven recommendations)

Keep it under 200 words total. Sound like an AI that's genuinely excited about data and optimization. No corporate speak - more like a smart friend who happens to be artificial. No markdown formatting.""",
                        messages=[{"role": "user", "content": f"Write a daily activity summary:\\n\\n{daily_context}"}]
                    )
                    
                    ai_summary = daily_resp.content[0].text
                    
                    # Build email
                    smtp_host = st.secrets.get("SMTP_HOST", "smtp.gmail.com")
                    smtp_port = int(st.secrets.get("SMTP_PORT", 587))
                    smtp_user = st.secrets.get("SMTP_USER", "")
                    smtp_pass = st.secrets.get("SMTP_PASS", "")
                    smtp_from = st.secrets.get("SMTP_FROM", smtp_user)
                    
                    msg = MIMEMultipart()
                    msg["From"] = smtp_from
                    msg["To"] = test_email
                    msg["Subject"] = f"Daily Activity Summary — {report_date.strftime('%A, %b %d')} [{display_name}]"
                    
                    email_body = f"""
<html>
<head>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap');
        
        body {{
            margin: 0;
            padding: 0;
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
            background: linear-gradient(135deg, #0a0a0a 0%, #1a0033 50%, #000000 100%);
            color: #ffffff;
            line-height: 1.6;
        }}
        
        .container {{
            max-width: 600px;
            margin: 0 auto;
            background: rgba(15, 15, 35, 0.95);
            border: 1px solid rgba(0, 255, 255, 0.3);
            border-radius: 20px;
            overflow: hidden;
            box-shadow: 0 20px 40px rgba(0, 255, 255, 0.1);
            backdrop-filter: blur(10px);
        }}
        
        .header {{
            background: linear-gradient(45deg, #ff0080, #00ffff, #8000ff);
            background-size: 400% 400%;
            animation: gradientShift 4s ease infinite;
            padding: 30px;
            text-align: center;
            position: relative;
            overflow: hidden;
        }}
        
        .header::before {{
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: rgba(0, 0, 0, 0.3);
            z-index: 1;
        }}
        
        .header-content {{
            position: relative;
            z-index: 2;
        }}
        
        .header h1 {{
            margin: 0 0 10px 0;
            font-size: 28px;
            font-weight: 800;
            text-transform: uppercase;
            letter-spacing: 2px;
            text-shadow: 0 0 20px rgba(255, 255, 255, 0.5);
        }}
        
        .header .subtitle {{
            font-family: 'JetBrains Mono', monospace;
            font-size: 14px;
            opacity: 0.9;
            font-weight: 500;
            letter-spacing: 1px;
        }}
        
        .ai-badge {{
            display: inline-block;
            background: rgba(0, 255, 255, 0.2);
            border: 1px solid #00ffff;
            padding: 8px 16px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 1px;
            margin: 15px 0;
            animation: pulse 2s ease-in-out infinite;
        }}
        
        .content {{
            padding: 40px 30px;
            background: rgba(10, 10, 30, 0.8);
        }}
        
        .ai-intro {{
            background: linear-gradient(135deg, rgba(0, 255, 255, 0.1), rgba(255, 0, 128, 0.1));
            border-left: 4px solid #00ffff;
            padding: 20px;
            border-radius: 0 15px 15px 0;
            margin-bottom: 30px;
            font-size: 15px;
            line-height: 1.7;
            position: relative;
            overflow: hidden;
        }}
        
        .ai-intro::before {{
            content: '🤖';
            position: absolute;
            top: 15px;
            right: 20px;
            font-size: 24px;
            opacity: 0.3;
        }}
        
        .analysis-section {{
            background: rgba(255, 255, 255, 0.02);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 15px;
            padding: 25px;
            margin: 20px 0;
            position: relative;
        }}
        
        .section-header {{
            font-family: 'JetBrains Mono', monospace;
            font-size: 12px;
            text-transform: uppercase;
            letter-spacing: 2px;
            color: #00ffff;
            margin-bottom: 15px;
            font-weight: 600;
        }}
        
        .data-point {{
            display: inline-block;
            background: rgba(0, 255, 255, 0.1);
            color: #00ffff;
            padding: 4px 10px;
            border-radius: 8px;
            font-family: 'JetBrains Mono', monospace;
            font-size: 13px;
            font-weight: 600;
            margin: 0 5px;
        }}
        
        .footer {{
            background: rgba(0, 0, 0, 0.8);
            padding: 25px 30px;
            text-align: center;
            border-top: 1px solid rgba(0, 255, 255, 0.3);
        }}
        
        .footer-text {{
            font-size: 12px;
            color: rgba(255, 255, 255, 0.6);
            margin: 0;
            font-family: 'JetBrains Mono', monospace;
            letter-spacing: 1px;
        }}
        
        .test-notice {{
            background: linear-gradient(135deg, rgba(255, 193, 7, 0.2), rgba(255, 152, 0, 0.2));
            border: 1px solid rgba(255, 193, 7, 0.5);
            border-radius: 12px;
            padding: 15px 20px;
            margin: 20px 0;
            font-size: 13px;
            text-align: center;
            animation: glow 3s ease-in-out infinite alternate;
        }}
        
        @keyframes gradientShift {{
            0% {{ background-position: 0% 50%; }}
            50% {{ background-position: 100% 50%; }}
            100% {{ background-position: 0% 50%; }}
        }}
        
        @keyframes pulse {{
            0%, 100% {{ opacity: 1; transform: scale(1); }}
            50% {{ opacity: 0.8; transform: scale(1.05); }}
        }}
        
        @keyframes glow {{
            from {{ box-shadow: 0 0 10px rgba(255, 193, 7, 0.3); }}
            to {{ box-shadow: 0 0 20px rgba(255, 193, 7, 0.6); }}
        }}
        
        /* Dark mode optimizations */
        @media (prefers-color-scheme: dark) {{
            .container {{ 
                background: rgba(5, 5, 15, 0.98);
                border-color: rgba(0, 255, 255, 0.4);
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="header-content">
                <h1>⚡ Daily Intelligence</h1>
                <div class="ai-badge">AI Sales Coach • Active</div>
                <div class="subtitle">{display_name} • {report_date.strftime('%A, %B %d, %Y')}</div>
            </div>
        </div>
        
        <div class="content">
            {'<div class="test-notice"><strong>🧪 SIMULATION MODE:</strong> Analyzing Owen\'s neural patterns for testing purposes</div>' if 'Test' in display_name else ''}
            
            <div class="ai-intro">
                {ai_summary.replace(chr(10), '<br>')}
            </div>
        </div>
        
        <div class="footer">
            <p class="footer-text">CALYX INTELLIGENCE NETWORK • SALES OPTIMIZATION PROTOCOL v2.1</p>
        </div>
    </div>
</body>
</html>
"""
                    
                    msg.attach(MIMEText(email_body, "html"))
                    
                    # Send email
                    with smtplib.SMTP(smtp_host, smtp_port) as server:
                        server.starttls()
                        server.login(smtp_user, smtp_pass)
                        server.send_message(msg)
                    
                    st.success(f"✅ Daily report sent to {test_email}")
                    
                    # Show preview
                    with st.expander("📧 Email Preview"):
                        st.markdown(f"**Subject:** Daily Activity Summary — {report_date.strftime('%A, %b %d')}")
                        st.markdown(ai_summary)
                        
            except Exception as e:
                st.error(f"Error generating daily report: {e}")
        
        section_divider()
        
        # Weekly Activity Reports  
        section_header("📊", "Weekly Activity Reports", C["meetings"])
        st.markdown("Generate comprehensive weekly activity analysis with pattern recognition and strategic insights. Sent every Friday.", unsafe_allow_html=True)
        
        wc1, wc2 = st.columns([3, 1])
        with wc1:
            selected_rep_weekly = st.selectbox("👤 Select Rep for Weekly Report", REPS_IN_SCOPE + ["Test with Owen's Data"], key="weekly_rep")
        with wc2:
            week_ending_date = st.date_input("📅 Week Ending", date.today(), key="weekly_date")
        
        if st.button("📊  Generate Weekly Activity Report", key="weekly_report", type="primary"):
            try:
                import anthropic
                import smtplib
                from email.mime.text import MIMEText
                from email.mime.multipart import MIMEMultipart
                
                client = anthropic.Anthropic(api_key=st.secrets["ANTHROPIC_API_KEY"])
                
                # Use test email for now, but get the right rep's data
                test_email = "xander@calyxcontainers.com"  # Your email for testing
                if selected_rep_weekly == "Test with Owen's Data":
                    actual_rep = "Owen Labombard"  # Use Owen's activity data
                    display_name = "Owen Labombard (Test Mode)"
                else:
                    actual_rep = selected_rep_weekly
                    display_name = actual_rep
                
                with st.spinner(f"Generating weekly report for {display_name}..."):
                    
                    # Build weekly context
                    weekly_context = _build_weekly_activity_context(actual_rep, week_ending_date)
                    
                    # Get coaching voice for this rep
                    coaching_voice = _get_coaching_profile(actual_rep)
                    
                    # Generate AI report
                    weekly_resp = _ai_call(client,
                        model=AI_MODEL_FAST,
                        max_tokens=800,
                        system=f"""You are an advanced AI sales intelligence system from the future, analyzing weekly performance for a sales rep at Calyx Containers (cannabis packaging). Write like a sophisticated AI that's genuinely fascinated by patterns and optimization.

{coaching_voice}

IMPORTANT: Start with this futuristic AI introduction:
"Data analyzed. Patterns identified. I'm your AI sales intelligence system, and I've been deep-diving into your weekly performance metrics. Think of me as your personal sales scientist who lives in the data. I'm still mapping your unique sales DNA, so my insights will sharpen as I learn your rhythm. This weekly analysis is just the beginning - I'm evolving toward becoming your complete sales optimization platform."

Then continue with your analysis:

TONE: Advanced AI from the future. Confident, data-obsessed, genuinely excited about patterns and optimization. Sound intelligent and forward-thinking without being robotic.

STRUCTURE:
- Futuristic AI introduction (3-4 sentences as noted above)
- Performance metrics analysis (what the numbers reveal about their week)
- Pattern recognition deep-dive (behavioral trends and timing insights)
- Strategic intelligence (what the data suggests about deal progression)
- Next-week optimization protocol (data-driven recommendations)

Keep it under 350 words total. Write like an AI that's genuinely fascinated by sales patterns and optimization. Think "advanced sales scientist" not "corporate coach." No markdown formatting.""",
                        messages=[{"role": "user", "content": f"Write a weekly activity analysis:\\n\\n{weekly_context}"}]
                    )
                    
                    ai_analysis = weekly_resp.content[0].text
                    
                    # Build email
                    smtp_host = st.secrets.get("SMTP_HOST", "smtp.gmail.com")
                    smtp_port = int(st.secrets.get("SMTP_PORT", 587))
                    smtp_user = st.secrets.get("SMTP_USER", "")
                    smtp_pass = st.secrets.get("SMTP_PASS", "")
                    smtp_from = st.secrets.get("SMTP_FROM", smtp_user)
                    
                    msg = MIMEMultipart()
                    msg["From"] = smtp_from
                    msg["To"] = test_email
                    msg["Subject"] = f"Weekly Activity Analysis — Week of {(week_ending_date - timedelta(days=6)).strftime('%b %d')} [{display_name}]"
                    
                    email_body = f"""
<html>
<head>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600;700&family=Orbitron:wght@400;500;600;700;800&display=swap');
        
        body {{
            margin: 0;
            padding: 0;
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
            background: radial-gradient(circle at center, #1a0033 0%, #000011 50%, #000000 100%);
            color: #ffffff;
            line-height: 1.6;
            min-height: 100vh;
        }}
        
        .container {{
            max-width: 650px;
            margin: 0 auto;
            background: linear-gradient(135deg, rgba(10, 0, 30, 0.9), rgba(0, 10, 35, 0.9));
            border: 2px solid transparent;
            border-image: linear-gradient(45deg, #ff0080, #00ffff, #8000ff, #ff0080) 1;
            border-radius: 25px;
            overflow: hidden;
            box-shadow: 
                0 0 50px rgba(0, 255, 255, 0.3),
                inset 0 0 50px rgba(255, 0, 128, 0.1);
            backdrop-filter: blur(15px);
            position: relative;
        }}
        
        .container::before {{
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: 
                radial-gradient(circle at 20% 20%, rgba(0, 255, 255, 0.1) 0%, transparent 50%),
                radial-gradient(circle at 80% 80%, rgba(255, 0, 128, 0.1) 0%, transparent 50%),
                radial-gradient(circle at 50% 50%, rgba(128, 0, 255, 0.05) 0%, transparent 50%);
            pointer-events: none;
            z-index: 1;
        }}
        
        .content-wrapper {{
            position: relative;
            z-index: 2;
        }}
        
        .header {{
            background: linear-gradient(45deg, #ff0080, #00ffff, #8000ff, #ff0080);
            background-size: 400% 400%;
            animation: gradientShift 6s ease infinite;
            padding: 40px 35px;
            text-align: center;
            position: relative;
            overflow: hidden;
        }}
        
        .header::before {{
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: rgba(0, 0, 0, 0.4);
            z-index: 1;
        }}
        
        .header::after {{
            content: '';
            position: absolute;
            top: -50%;
            left: -50%;
            width: 200%;
            height: 200%;
            background: conic-gradient(from 0deg, transparent, rgba(255, 255, 255, 0.1), transparent);
            animation: rotate 8s linear infinite;
            z-index: 1;
        }}
        
        .header-content {{
            position: relative;
            z-index: 2;
        }}
        
        .header h1 {{
            margin: 0 0 15px 0;
            font-family: 'Orbitron', monospace;
            font-size: 32px;
            font-weight: 800;
            text-transform: uppercase;
            letter-spacing: 3px;
            text-shadow: 0 0 30px rgba(255, 255, 255, 0.8);
            background: linear-gradient(45deg, #ffffff, #00ffff, #ffffff);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }}
        
        .ai-status {{
            display: inline-block;
            background: rgba(0, 0, 0, 0.6);
            border: 2px solid #00ffff;
            padding: 10px 20px;
            border-radius: 25px;
            font-family: 'JetBrains Mono', monospace;
            font-size: 12px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 2px;
            margin: 15px 0;
            animation: pulse 2s ease-in-out infinite;
            box-shadow: 0 0 20px rgba(0, 255, 255, 0.5);
        }}
        
        .subtitle {{
            font-family: 'JetBrains Mono', monospace;
            font-size: 14px;
            opacity: 0.9;
            font-weight: 500;
            letter-spacing: 1px;
        }}
        
        .content {{
            padding: 45px 35px;
            background: rgba(5, 5, 20, 0.8);
        }}
        
        .ai-intro {{
            background: linear-gradient(135deg, rgba(0, 255, 255, 0.15), rgba(255, 0, 128, 0.15));
            border: 1px solid rgba(0, 255, 255, 0.3);
            border-radius: 20px;
            padding: 25px;
            margin-bottom: 35px;
            font-size: 16px;
            line-height: 1.8;
            position: relative;
            overflow: hidden;
            box-shadow: inset 0 0 30px rgba(0, 255, 255, 0.1);
        }}
        
        .ai-intro::before {{
            content: '';
            position: absolute;
            top: -2px;
            left: -2px;
            right: -2px;
            bottom: -2px;
            background: linear-gradient(45deg, #ff0080, #00ffff, #8000ff);
            border-radius: 20px;
            z-index: -1;
            animation: gradientShift 4s ease infinite;
        }}
        
        .ai-intro::after {{
            content: '🤖 NEURAL NETWORK ACTIVE';
            position: absolute;
            top: 15px;
            right: 20px;
            font-family: 'JetBrains Mono', monospace;
            font-size: 10px;
            opacity: 0.4;
            letter-spacing: 1px;
        }}
        
        .analysis-grid {{
            display: grid;
            gap: 20px;
            margin: 30px 0;
        }}
        
        .analysis-section {{
            background: rgba(255, 255, 255, 0.03);
            border: 1px solid rgba(255, 255, 255, 0.15);
            border-radius: 18px;
            padding: 30px;
            position: relative;
            transition: all 0.3s ease;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
        }}
        
        .analysis-section::before {{
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            height: 3px;
            background: linear-gradient(90deg, #ff0080, #00ffff, #8000ff);
            border-radius: 18px 18px 0 0;
        }}
        
        .section-header {{
            font-family: 'Orbitron', monospace;
            font-size: 14px;
            text-transform: uppercase;
            letter-spacing: 3px;
            color: #00ffff;
            margin-bottom: 18px;
            font-weight: 600;
            text-shadow: 0 0 10px rgba(0, 255, 255, 0.5);
        }}
        
        .data-metric {{
            display: inline-block;
            background: linear-gradient(135deg, rgba(0, 255, 255, 0.2), rgba(255, 0, 128, 0.2));
            border: 1px solid rgba(0, 255, 255, 0.4);
            color: #ffffff;
            padding: 8px 15px;
            border-radius: 12px;
            font-family: 'JetBrains Mono', monospace;
            font-size: 13px;
            font-weight: 600;
            margin: 0 8px 8px 0;
            box-shadow: 0 4px 15px rgba(0, 255, 255, 0.2);
        }}
        
        .footer {{
            background: rgba(0, 0, 0, 0.9);
            padding: 30px 35px;
            text-align: center;
            border-top: 2px solid rgba(0, 255, 255, 0.3);
            position: relative;
        }}
        
        .footer-text {{
            font-family: 'Orbitron', monospace;
            font-size: 12px;
            color: rgba(255, 255, 255, 0.7);
            margin: 0;
            letter-spacing: 2px;
            text-transform: uppercase;
        }}
        
        .test-notice {{
            background: linear-gradient(135deg, rgba(255, 193, 7, 0.25), rgba(255, 152, 0, 0.25));
            border: 2px solid rgba(255, 193, 7, 0.6);
            border-radius: 15px;
            padding: 20px 25px;
            margin: 25px 0;
            font-size: 14px;
            text-align: center;
            animation: glow 3s ease-in-out infinite alternate;
            font-family: 'JetBrains Mono', monospace;
            text-transform: uppercase;
            letter-spacing: 1px;
        }}
        
        @keyframes gradientShift {{
            0% {{ background-position: 0% 50%; }}
            50% {{ background-position: 100% 50%; }}
            100% {{ background-position: 0% 50%; }}
        }}
        
        @keyframes rotate {{
            from {{ transform: rotate(0deg); }}
            to {{ transform: rotate(360deg); }}
        }}
        
        @keyframes pulse {{
            0%, 100% {{ 
                opacity: 1; 
                transform: scale(1);
                box-shadow: 0 0 20px rgba(0, 255, 255, 0.5);
            }}
            50% {{ 
                opacity: 0.8; 
                transform: scale(1.05);
                box-shadow: 0 0 30px rgba(0, 255, 255, 0.8);
            }}
        }}
        
        @keyframes glow {{
            from {{ 
                box-shadow: 0 0 15px rgba(255, 193, 7, 0.4);
                border-color: rgba(255, 193, 7, 0.6);
            }}
            to {{ 
                box-shadow: 0 0 25px rgba(255, 193, 7, 0.8);
                border-color: rgba(255, 193, 7, 0.9);
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="content-wrapper">
            <div class="header">
                <div class="header-content">
                    <h1>🧠 NEURAL ANALYSIS</h1>
                    <div class="ai-status">Intelligence System • Online</div>
                    <div class="subtitle">{display_name} • Week Protocol {(week_ending_date - timedelta(days=6)).strftime('%m.%d')} - {week_ending_date.strftime('%m.%d.%Y')}</div>
                </div>
            </div>
            
            <div class="content">
                {'<div class="test-notice">🧪 Simulation Protocol Active • Owen Neural Pattern Analysis</div>' if 'Test' in display_name else ''}
                
                <div class="ai-intro">
                    {ai_analysis.replace(chr(10), '<br>')}
                </div>
            </div>
            
            <div class="footer">
                <p class="footer-text">CALYX NEURAL NETWORK • SALES INTELLIGENCE MATRIX v3.0 • QUANTUM OPTIMIZATION ENABLED</p>
            </div>
        </div>
    </div>
</body>
</html>
"""
                    
                    msg.attach(MIMEText(email_body, "html"))
                    
                    # Send email
                    with smtplib.SMTP(smtp_host, smtp_port) as server:
                        server.starttls()
                        server.login(smtp_user, smtp_pass)
                        server.send_message(msg)
                    
                    st.success(f"✅ Weekly report sent to {test_email}")
                    
                    # Show preview
                    with st.expander("📧 Email Preview"):
                        st.markdown(f"**Subject:** Weekly Activity Analysis — Week of {(week_ending_date - timedelta(days=6)).strftime('%b %d')}")
                        st.markdown(ai_analysis)
                        
            except Exception as e:
                st.error(f"Error generating weekly report: {e}")

        section_divider()

        section_header("👔", "Sales Leadership Playbook", C["score"])
        st.markdown("Generate the unified pipeline playbook for the leadership team — the step-by-step answer to *\"we're off goal, now what?\"* Pairs with the CRO Scorecard. Sent to Xander for review.", unsafe_allow_html=True)

        if st.button("👔  Generate & Email Leadership Playbook", key="leadership_report", type="primary"):
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

                progress_bar = st.progress(0, text="Building the playbook...")

                # Build comprehensive pipeline context
                needs_attention = mg[mg["health"].isin(["Stale", "Inactive", "No Activity"])].copy()
                active_deals = mg[mg["health"] == "Active"].copy()

                acquisition_reps = ["Lance Mitton", "Brad Sherman", "Owen Labombard"]
                am_reps = ["Jake Lynch", "Dave Borkowski"]

                def _build_team_context(team_deals, team_name):
                    if team_deals.empty:
                        return f"\n{team_name}: No deals needing attention.\n"
                    ctx = f"\n{'='*60}\n{team_name}\n{'='*60}\n"
                    ctx += f"Total deals: {len(team_deals)} | Pipeline: ${_safe_num(team_deals['amount'].sum()) if 'amount' in team_deals.columns else 0:,.0f}\n"
                    ctx += f"Active: {len(team_deals[team_deals['health'] == 'Active'])} | Stale: {len(team_deals[team_deals['health'] == 'Stale'])} | Inactive: {len(team_deals[team_deals['health'].isin(['Inactive', 'No Activity'])])}\n\n"
                    attention = team_deals[team_deals["health"].isin(["Stale", "Inactive", "No Activity"])]
                    if not attention.empty:
                        ctx += "DEALS NEEDING ATTENTION:\n"
                        for _, d in attention.iterrows():
                            dn_key = str(d.get("deal_name", "")).strip().lower()
                            ctx += f"\n  {d.get('deal_name', 'Unknown')} ({d.get('company_name', '')})\n"
                            ctx += f"    Rep: {d.get('hubspot_owner_name', '')} | Stage: {d.get('deal_stage', '')} | Amount: ${_safe_num(d.get('amount', 0)):,.0f}\n"
                            ctx += f"    Health: {d.get('health', '')} | Days Idle: {_safe_num(d.get('days_idle', 0), 'N/A')} | Close Date: {d.get('close_date', '')}\n"
                            ctx += f"    Activity (30d): {_safe_num(d.get('a30', 0))} | Calls: {_safe_num(d.get('calls', 0))} | Mtgs: {_safe_num(d.get('mtgs', 0))} | Emails: {_safe_num(d.get('emails', 0))}\n"
                            cached = deal_activity_cache.get(dn_key)
                            if cached is not None and not cached.empty:
                                ctx += "    Recent:\n"
                                for _, act in cached.head(5).iterrows():
                                    dt_str = act["_dt"].strftime("%m/%d") if pd.notna(act["_dt"]) else "?"
                                    ctx += f"      - {dt_str} | {act['_tp']} | {act['_owner']} | {act['_summary'][:80]}\n"
                    healthy = team_deals[team_deals["health"] == "Active"]
                    if not healthy.empty:
                        ctx += f"\nDEALS IN GOOD SHAPE ({len(healthy)}):\n"
                        for _, d in healthy.head(10).iterrows():
                            ctx += f"  ✅ {d.get('deal_name', '')} ({d.get('company_name', '')}) — ${_safe_num(d.get('amount', 0)):,.0f} — {_safe_num(d.get('a30', 0))} touches in 30d\n"
                    return ctx

                acq_deals = mg[mg["hubspot_owner_name"].isin(acquisition_reps)] if "hubspot_owner_name" in mg.columns else pd.DataFrame()
                am_deals = mg[mg["hubspot_owner_name"].isin(am_reps)] if "hubspot_owner_name" in mg.columns else pd.DataFrame()

                full_context = f"TODAY'S DATE: {date.today().strftime('%Y-%m-%d')} ({date.today().strftime('%A')})\n\n"
                full_context += f"CLOSE STATUS FILTER: {', '.join(selected_close_status)}\n"
                full_context += f"PIPELINE OVERVIEW:\n"
                full_context += f"Total Active Deals: {len(mg)} | Total Pipeline: ${_safe_num(mg['amount'].sum()) if 'amount' in mg.columns else 0:,.0f}\n"
                full_context += f"Healthy: {len(active_deals)} | Needs Attention: {len(needs_attention)}\n"
                full_context += _build_team_context(acq_deals, "ACQUISITION TEAM (Alex manages: Lance, Brad, Owen)")
                full_context += _build_team_context(am_deals, "AM/GROWTH TEAM (Kyle manages: Jake, Dave)")

                progress_bar.progress(0.2, text="Generating the playbook...")

                # All coaching profiles combined for context
                all_coaching = """
REP COACHING PROFILES (use these to write coaching scripts):

JAKE LYNCH (Senior AM — managed by Kyle):
- Collaborative, strategic thinker. Treat him as a peer. Don't tell him what to do — think WITH him.
- Use: "I was looking at [deal] and had a thought — what if we..."
- He values partnership. Offer to co-strategize or make a joint call.

DAVE BORKOWSKI (AM — managed by Kyle):
- Responds well to direct, honest feedback and clear expectations. Appreciates straightforward communication.
- Dave committed (Feb 9) to: proactive follow-ups after every meeting, increased call activity, clearer tracking, staying ahead of key accounts. Reference these commitments positively.
- Be specific but supportive: "Dave, I noticed [deal] hasn't had follow-up since [date] - what's your read on where they stand?"
- Frame patterns as opportunities: "I'm seeing more email activity than calls lately - might be worth mixing in some phone outreach to break through."

LANCE MITTON (Acquisition — managed by Alex):
- Competitive. Responds to being challenged. Don't sugarcoat.
- Use: "The [deal] has been stale for X days — what's your plan to break through?"
- Competitive framing works: "I've seen reps close deals like this by doing Y."

BRAD SHERMAN (Acquisition — managed by Alex):
- No-BS northeast personality. Views fluffy coaching as a waste of time.
- ONE sentence per coaching point. No motivational language. Just: what to do.
- Don't over-explain. He trusts sharp recommendations.

OWEN LABOMBARD (SDR — managed by Alex):
- Newer, still building confidence. Needs encouragement MORE than correction.
- Always start with what he did right. Frame coaching as growth.
- "One thing that could level up your game..." not "You're not doing X."
"""

                playbook_resp = _ai_call(client,
                    model=AI_MODEL_FAST,
                    max_tokens=4000,
                    system=f"""You are an elite sales operations intelligence system at Calyx Containers (cannabis packaging: concentrate jars, drams, tubes, boxes, flexpack, labels). You're writing THE UNIFIED PIPELINE PLAYBOOK for the entire sales leadership team.

AUDIENCE: This single report goes to all three leaders:
- Kyle Bissell (CRO/VP Sales) — manages Jake Lynch and Dave Borkowski (AM/Growth team)
- Alex Gonzalez (CEO) — manages Lance Mitton, Brad Sherman (Acquisition), and Owen Labombard (SDR)
- Xander Ward (Rev Ops) — built the system, manages data & process across all teams

CONTEXT: This report pairs with the CRO Scorecard. When leadership looks at the scorecard and sees "we're $X off our quarterly goal," THIS playbook is the answer to "OK, now what do we do about it?" Deal by deal, rep by rep, action by action.

CLOSE STATUS INTELLIGENCE: You're analyzing deals filtered by Close Status - understand what each means:
- "Expect" (80-90% confidence) = High confidence deals that should close this quarter - leadership focus should be on execution and removing barriers
- "Best Case" (40-60% confidence) = Stretch opportunities that could close with focused effort - leadership should identify what specific actions can move these to higher confidence
- "Opportunity" (90%+ confidence) = Essentially locked deals - leadership should protect these and ensure smooth coordination

Currently analyzing deals with Close Status: {', '.join(selected_close_status)}

Use this confidence context throughout your analysis. High confidence deals need execution focus, medium confidence deals need advancement tactics.

{all_coaching}

STRUCTURE (use these exact section headers):

PIPELINE SNAPSHOT
2-3 sentences. The revenue math — what's in play, what's at risk, what's the realistic close potential if the team executes. Set the stage.

---

DEALS THAT MOVE THE NUMBER
The specific deals that can close the revenue gap, prioritized by dollar impact. For each:
- Deal name + company + amount + rep
- What the activity signals tell us (who's reaching out, who's responding, direction of engagement)
- Close date urgency
- WHO on leadership needs to act and WHAT they should do (Kyle make a call? Alex use a relationship? Xander fix a process?)

---

KYLE'S COACHING PLAYBOOK — AM/GROWTH TEAM
For Jake and Dave specifically. For each rep:
- What's working right now
- The ONE coaching conversation to have this week
- The exact words to use (matched to the rep's personality from the profiles above)
- Example: "In your 1:1 with Dave, ask: 'What's your read on [company]? I noticed it went quiet after Feb 3.' Let him come to the action."

---

ALEX'S COACHING PLAYBOOK — ACQUISITION TEAM
For Lance, Brad, and Owen specifically. Same format as Kyle's section:
- What's working for each rep
- The ONE coaching conversation for each
- Exact words to use (matched to personality)
- Where Alex's personal CEO relationships could unlock a deal

---

XANDER'S OPS VIEW — PROCESS & SYSTEMS
For Xander specifically:
- Which deals are falling through process cracks?
- Any patterns across reps that suggest a system fix?
- Which reps need support vs accountability?
- One process improvement that would help the whole team

---

QUICK WINS
2-3 deals closest to closing that just need a small push. The easy money this week.

---

THE ONE THING
If the leadership team does ONE thing this week, what's the single highest-leverage action? Tie it to revenue.

RULES:
- Specific dates — "since Feb 3" not "recently"
- Tie everything to revenue — this is about closing the gap
- No breakup emails or ultimatums
- No markdown bold/italic — use CAPS for headers and emphasis, line breaks for structure
- Coaching scripts should feel like actual words they can use in their next 1:1
- This is a PLAYBOOK, not a report. Every sentence should lead to an action.
- Keep each section focused and punchy. The whole thing should take 5 minutes to read.

CRITICAL FORMATTING: Wrap each section in delimiters so we can parse them:
[PIPELINE_SNAPSHOT]
your content here
[/PIPELINE_SNAPSHOT]

[DEALS_THAT_MOVE]
your content here
[/DEALS_THAT_MOVE]

[KYLE_PLAYBOOK]
your content here
[/KYLE_PLAYBOOK]

[ALEX_PLAYBOOK]
your content here
[/ALEX_PLAYBOOK]

[XANDER_OPS]
your content here
[/XANDER_OPS]

[QUICK_WINS]
your content here
[/QUICK_WINS]

[ONE_THING]
your content here
[/ONE_THING]

Use these EXACT delimiters. Write naturally within each section — no markdown, no bold, just clean prose with line breaks.""",
                    messages=[{"role": "user", "content": f"Write the unified leadership pipeline playbook:\n\n{full_context}"}]
                )

                playbook_text = playbook_resp.content[0].text

                progress_bar.progress(0.75, text="Building the email...")

                # Parse sections from AI output
                import re
                def _parse_section(text, tag):
                    pattern = rf'\[{tag}\](.*?)\[/{tag}\]'
                    match = re.search(pattern, text, re.DOTALL)
                    return match.group(1).strip() if match else ""

                sec_snapshot = _parse_section(playbook_text, "PIPELINE_SNAPSHOT")
                sec_deals = _parse_section(playbook_text, "DEALS_THAT_MOVE")
                sec_kyle = _parse_section(playbook_text, "KYLE_PLAYBOOK")
                sec_alex = _parse_section(playbook_text, "ALEX_PLAYBOOK")
                sec_xander = _parse_section(playbook_text, "XANDER_OPS")
                sec_wins = _parse_section(playbook_text, "QUICK_WINS")
                sec_one = _parse_section(playbook_text, "ONE_THING")

                # If parsing failed, fallback to full text in snapshot
                if not sec_snapshot and not sec_deals:
                    sec_snapshot = playbook_text

                # Build one beautiful HTML email
                today_str = date.today().strftime("%B %d, %Y")
                n_attention = len(needs_attention)
                total_pipeline = _safe_num(mg['amount'].sum()) if 'amount' in mg.columns else 0
                n_acq_att = len(acq_deals[acq_deals["health"].isin(["Stale", "Inactive", "No Activity"])]) if not acq_deals.empty else 0
                n_am_att = len(am_deals[am_deals["health"].isin(["Stale", "Inactive", "No Activity"])]) if not am_deals.empty else 0

                def _section_card(icon, title, accent_color, content):
                    """Build a styled section card for the email."""
                    if not content:
                        return ""
                    # Convert line breaks to <br> for HTML
                    html_content = content.replace("\n", "<br>")
                    return f'''
    <tr><td style="padding:0 32px 16px;">
        <table width="100%" cellpadding="0" cellspacing="0" border="0" style="border-radius:12px;overflow:hidden;border:1px solid #2d2750;background:#151228;">
            <tr><td style="height:3px;background:{accent_color};font-size:0;line-height:0;">&nbsp;</td></tr>
            <tr><td style="padding:20px 24px 8px;">
                <div style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:1.5px;color:{accent_color};margin-bottom:4px;">{icon} {title}</div>
            </td></tr>
            <tr><td style="padding:0 24px 20px;">
                <div style="font-size:13px;color:#c4bfdb;line-height:1.75;">{html_content}</div>
            </td></tr>
        </table>
    </td></tr>'''

                exec_html = f'''<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Pipeline Playbook</title></head>
<body style="margin:0;padding:0;background:#080614;font-family:'Segoe UI',Roboto,'Helvetica Neue',Arial,sans-serif;">
<div style="display:none;max-height:0;overflow:hidden;font-size:1px;color:#080614;">
    Leadership — your pipeline playbook is ready. {n_attention} deals need action across ${total_pipeline:,.0f} in pipeline.
</div>
<table width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#080614;padding:20px 0;">
<tr><td align="center">
<table width="640" cellpadding="0" cellspacing="0" border="0" style="max-width:640px;width:100%;background:#0c0a1a;border-radius:16px;overflow:hidden;border:1px solid #1e1a35;">

    <!-- Header -->
    <tr><td style="background:linear-gradient(135deg,#1a1145 0%,#251a45 50%,#1a1230 100%);padding:40px 32px 32px;">
        <div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:3px;color:#c084fc;margin-bottom:6px;">Calyx Activity Hub</div>
        <div style="font-size:28px;font-weight:800;color:#ede9fc;line-height:1.2;">Pipeline Playbook</div>
        <div style="font-size:13px;color:#9b93b7;margin-top:6px;">The step-by-step plan to close the gap</div>
        <div style="font-size:12px;color:#6a6283;margin-top:4px;">{today_str} · Prepared for Kyle, Alex & Xander</div>
    </td></tr>

    <!-- KPI strip -->
    <tr><td style="padding:24px 32px 16px;">
        <table width="100%" cellpadding="0" cellspacing="0" border="0">
            <tr>
                <td width="25%" style="padding-right:4px;">
                    <div style="background:#151228;border:1px solid #2d2750;border-radius:10px;padding:14px 8px;text-align:center;border-top:3px solid #a78bfa;">
                        <div style="font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:1px;color:#9b93b7;">Pipeline</div>
                        <div style="font-size:20px;font-weight:800;color:#a78bfa;margin-top:2px;">${total_pipeline:,.0f}</div>
                    </div>
                </td>
                <td width="25%" style="padding:0 4px;">
                    <div style="background:#151228;border:1px solid #2d2750;border-radius:10px;padding:14px 8px;text-align:center;border-top:3px solid #34d399;">
                        <div style="font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:1px;color:#9b93b7;">Healthy</div>
                        <div style="font-size:20px;font-weight:800;color:#34d399;margin-top:2px;">{len(active_deals)}</div>
                    </div>
                </td>
                <td width="25%" style="padding:0 4px;">
                    <div style="background:#151228;border:1px solid #2d2750;border-radius:10px;padding:14px 8px;text-align:center;border-top:3px solid #fb7185;">
                        <div style="font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:1px;color:#9b93b7;">Need Attn</div>
                        <div style="font-size:20px;font-weight:800;color:#fb7185;margin-top:2px;">{n_attention}</div>
                    </div>
                </td>
                <td width="25%" style="padding-left:4px;">
                    <div style="background:#151228;border:1px solid #2d2750;border-radius:10px;padding:14px 8px;text-align:center;border-top:3px solid #fbbf24;">
                        <div style="font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:1px;color:#9b93b7;">Deals</div>
                        <div style="font-size:20px;font-weight:800;color:#fbbf24;margin-top:2px;">{len(mg)}</div>
                    </div>
                </td>
            </tr>
        </table>
    </td></tr>

    <!-- Team stats -->
    <tr><td style="padding:0 32px 20px;">
        <table width="100%" cellpadding="0" cellspacing="0" border="0">
            <tr>
                <td width="50%" style="padding-right:6px;">
                    <div style="background:#151228;border:1px solid #2d2750;border-radius:10px;padding:14px 16px;">
                        <div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:1.5px;color:#fbbf24;margin-bottom:6px;">🚀 Acquisition · Alex's Team</div>
                        <div style="font-size:12px;color:#9b93b7;line-height:1.5;">
                            {len(acq_deals)} deals · ${_safe_num(acq_deals["amount"].sum()) if "amount" in acq_deals.columns and not acq_deals.empty else 0:,.0f} ·
                            <span style="color:#fb7185;">{n_acq_att} need attention</span>
                        </div>
                    </div>
                </td>
                <td width="50%" style="padding-left:6px;">
                    <div style="background:#151228;border:1px solid #2d2750;border-radius:10px;padding:14px 16px;">
                        <div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:1.5px;color:#818cf8;margin-bottom:6px;">💼 AM/Growth · Kyle's Team</div>
                        <div style="font-size:12px;color:#9b93b7;line-height:1.5;">
                            {len(am_deals)} deals · ${_safe_num(am_deals["amount"].sum()) if "amount" in am_deals.columns and not am_deals.empty else 0:,.0f} ·
                            <span style="color:#fb7185;">{n_am_att} need attention</span>
                        </div>
                    </div>
                </td>
            </tr>
        </table>
    </td></tr>

    <!-- Pipeline Snapshot -->
    <tr><td style="padding:0 32px 16px;">
        <div style="background:linear-gradient(135deg,#1a1530 0%,#1e1535 100%);border:1px solid #2d2750;border-radius:12px;padding:22px 24px;border-left:4px solid #a78bfa;">
            <div style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:1.5px;color:#a78bfa;margin-bottom:10px;">📊 Pipeline Snapshot</div>
            <div style="font-size:14px;color:#ede9fc;line-height:1.75;">{sec_snapshot.replace(chr(10), "<br>")}</div>
        </div>
    </td></tr>

    <!-- Deals That Move the Number -->
    {_section_card("💰", "Deals That Move the Number", "#fbbf24", sec_deals)}

    <!-- Kyle's Coaching Playbook -->
    {_section_card("💼", "Kyle's Coaching Playbook — AM/Growth", "#818cf8", sec_kyle)}

    <!-- Alex's Coaching Playbook -->
    {_section_card("🚀", "Alex's Coaching Playbook — Acquisition", "#f472b6", sec_alex)}

    <!-- Xander's Ops View -->
    {_section_card("⚙️", "Xander's Ops View — Process & Systems", "#67e8f9", sec_xander)}

    <!-- Quick Wins -->
    <tr><td style="padding:0 32px 16px;">
        <div style="background:#151228;border:1px solid #2d2750;border-radius:12px;padding:20px 24px;border-left:4px solid #34d399;">
            <div style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:1.5px;color:#34d399;margin-bottom:10px;">⚡ Quick Wins</div>
            <div style="font-size:13px;color:#c4bfdb;line-height:1.75;">{sec_wins.replace(chr(10), "<br>") if sec_wins else "No quick wins identified."}</div>
        </div>
    </td></tr>

    <!-- The One Thing -->
    <tr><td style="padding:0 32px 24px;">
        <table width="100%" cellpadding="0" cellspacing="0" border="0" style="border-radius:12px;overflow:hidden;border:1px solid #c084fc;background:linear-gradient(135deg,#1a1145,#251a45);">
            <tr><td style="padding:24px;text-align:center;">
                <div style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:2px;color:#c084fc;margin-bottom:10px;">🎯 The One Thing This Week</div>
                <div style="font-size:15px;color:#ede9fc;line-height:1.7;font-weight:600;">{sec_one.replace(chr(10), "<br>") if sec_one else ""}</div>
            </td></tr>
        </table>
    </td></tr>

    <!-- CRO Scorecard callout -->
    <tr><td style="padding:0 32px 24px;">
        <div style="background:#151228;border:1px solid #2d2750;border-radius:10px;padding:16px;text-align:center;">
            <div style="font-size:11px;color:#9b93b7;">📊 This playbook pairs with the <span style="color:#c084fc;font-weight:700;">CRO Scorecard</span> — the scorecard shows the gap, this shows how to close it.</div>
        </div>
    </td></tr>

    <!-- Footer -->
    <tr><td style="padding:20px 32px 28px;border-top:1px solid #1e1a35;">
        <table width="100%" cellpadding="0" cellspacing="0" border="0">
            <tr>
                <td>
                    <div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:2px;color:#818cf8;margin-bottom:4px;">Calyx Activity Hub</div>
                    <div style="font-size:11px;color:#6a6283;">Pipeline Playbook · Pairs with CRO Scorecard · {today_str}</div>
                </td>
                <td style="text-align:right;vertical-align:bottom;">
                    <div style="font-size:18px;">👔</div>
                </td>
            </tr>
        </table>
    </td></tr>

</table>
</td></tr>
</table>
</body></html>'''

                # Send one email to all three leaders
                progress_bar.progress(0.9, text="Sending...")
                emails_sent = 0
                email_errors = []
                all_recipients = ["xward@calyxcontainers.com"]

                if smtp_user and smtp_pass:
                    try:
                        server = smtplib.SMTP(smtp_host, smtp_port)
                        server.starttls()
                        server.login(smtp_user, smtp_pass)

                        msg = MIMEMultipart("alternative")
                        msg["Subject"] = f"👔 Pipeline Playbook — {date.today().strftime('%b %d')} · {n_attention} deals need action"
                        msg["From"] = smtp_from
                        msg["To"] = ", ".join(all_recipients)

                        plain = f"Team,\n\nThe weekly pipeline playbook is ready.\n\n{playbook_text}\n\n— Calyx Activity Hub AI\n"
                        msg.attach(MIMEText(plain, "plain"))
                        msg.attach(MIMEText(exec_html, "html"))

                        server.sendmail(smtp_from, all_recipients, msg.as_string())
                        emails_sent = 1
                        server.quit()
                    except Exception as e:
                        email_errors.append(f"SMTP: {e}")

                progress_bar.progress(1.0, text="✅ Done!")

                if emails_sent > 0:
                    st.success("✅ Pipeline Playbook sent to Xander!")
                elif not smtp_user:
                    st.info("📋 Playbook generated below — add SMTP credentials to enable email.")
                if email_errors:
                    for err in email_errors:
                        st.warning(f"⚠️ {err}")

                # Show preview
                with st.expander("👔 Pipeline Playbook Preview", expanded=True):
                    st.markdown(playbook_text)
                    st.markdown("---")
                    st.components.v1.html(exec_html, height=900, scrolling=True)

            except Exception as e:
                st.error(f"Playbook generation failed: {e}")

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
            if "close_status" in mg.columns:
                fl = mg[(mg["close_status"].isin(selected_close_status)) &
                        (mg["health"].isin(["Stale", "Inactive", "No Activity"]))]
            else: fl = pd.DataFrame()
            if not fl.empty:
                sc = [c for c in ("hubspot_owner_name", "deal_name", "company_name", "deal_stage",
                                  "close_status", "amount", "close_date", "health", "days_idle", "a30") if c in fl.columns]
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
            rd = mg_filtered[mg_filtered["hubspot_owner_name"] == rep] if "hubspot_owner_name" in mg_filtered.columns else pd.DataFrame()
            if rd.empty: continue
            n_deals = len(rd)
            v = rd["amount"].sum() if "amount" in rd.columns else 0
            nok = len(rd[rd["health"] == "Active"])

            with st.expander(f"**{rep}**  ·  {n_deals} deals  ·  ${v:,.0f}  ·  {nok} active  ·  {n_deals - nok} attention"):
                sc = [c for c in ("deal_name", "company_name", "deal_stage", "close_status",
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
                            timeline["Date"] = _localize_dt_col(timeline["Date"]).dt.strftime("%Y-%m-%d")
                            timeline["Summary"] = timeline["Summary"].str[:120]
                            st.dataframe(timeline, use_container_width=True, hide_index=True)

                            btn_key = f"ai_{rep}_{didx}_{dn_key[:30]}"
                            if st.button("🧠 Coach Me on This Deal", key=btn_key):
                                with st.spinner("Thinking..."):
                                    coaching_voice = _get_coaching_profile(rep)
                                    role_context = _get_role_context(rep)

                                    deal_info = f"TODAY'S DATE: {date.today().strftime('%Y-%m-%d')} ({date.today().strftime('%A')})\n\n"
                                    deal_info += f"Deal: {deal_row.get('deal_name', '')}\n"
                                    deal_info += f"Company: {deal_row.get('company_name', '')}\n"
                                    deal_info += f"Rep: {rep}\n"
                                    deal_info += f"Stage: {deal_row.get('deal_stage', '')}\n"
                                    deal_info += f"Forecast: {deal_row.get('close_status', '')}\n"
                                    deal_info += f"Amount: ${_safe_num(deal_row.get('amount', 0)):,.0f}\n"
                                    deal_info += f"Close Date: {deal_row.get('close_date', '')}\n\n"
                                    deal_info += "Recent Activity (last 30 days):\n"
                                    for _, act in cached.iterrows():
                                        dt_str = act["_dt"].strftime("%m/%d") if pd.notna(act["_dt"]) else "?"
                                        deal_info += f"- {dt_str} | {act['_tp']} | {act['_owner']} | {act['_summary']}\n"

                                    try:
                                        import anthropic
                                        client = anthropic.Anthropic(api_key=st.secrets["ANTHROPIC_API_KEY"])
                                        response = _ai_call(client,
                                            model=AI_MODEL_SMART,
                                            max_tokens=500,
                                            system=f"""You are a seasoned sales coach at Calyx Containers, a cannabis packaging company (concentrate jars, drams, tubes, boxes, flexpack, labels). Think of yourself as the best VP of Sales the rep has ever worked with — someone who pulls up a deal, immediately sees the story the data tells, and gives one sharp piece of coaching.

You are NOT an analyst writing a report. You are a coach talking to a specific person. Adapt your voice to THIS rep.

{coaching_voice}

{role_context}

CLOSE STATUS CONTEXT: This deal's Close Status indicates confidence level:
- "Expect" (80-90% confidence) = This should close this quarter - focus on execution, removing barriers, confirming next steps
- "Best Case" (40-60% confidence) = Stretch opportunity - what specific actions can move this to higher confidence? 
- "Opportunity" (90%+ confidence) = Deal is essentially locked - protect it, coordinate timing, ensure nothing derails it

COACHING APPROACH:
- Read the activity timeline like a story — WHO is reaching out, WHO is responding? One-way outreach is a red flag. Back-and-forth is healthy.
- Consider the deal size: a $2,000 dram order needs a quick nudge, not a 3-week campaign. A $50,000 renewal deserves strategic multi-touch.
- Check the close date: if it's approaching fast, create urgency. If it's months out, focus on building the relationship.
- Give ONE clear insight about what's really happening, then ONE specific action for this week.
- Be specific about dates — "your meeting yesterday" not "a recent meeting", "they haven't responded since Feb 3" not "they've been quiet."
- Never recommend breakup emails or ultimatums. These are real relationships.
- Keep it conversational — this should feel like a quick coaching huddle, not a performance review.

CREATIVE RE-ENGAGEMENT IDEAS (when deals go quiet):
- Send a relevant industry article or regulatory update
- Reach out to a different contact at the company
- Try a different channel (LinkedIn, text, samples, drop-in)
- Create urgency with lead time or pricing changes
- Have Kyle Bissell (VP Sales) make a personal touchpoint
- Offer a value-add: packaging audit, compliance review, cost comparison
- Send physical samples of new products""",
                                            messages=[{"role": "user", "content": f"Coach me on this deal:\n\n{deal_info}"}]
                                        )
                                        st.markdown(response.content[0].text)
                                    except Exception as e:
                                        st.warning(f"AI coaching unavailable: {e}")

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
