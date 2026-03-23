"""
Calyx Activity Hub — Single-file Streamlit dashboard.

Reads HubSpot activity data from a Google Sheet (synced by Coefficient)
and displays calls, meetings, emails, deals, and tickets.

Secrets required (in .streamlit/secrets.toml or Streamlit Cloud):
  - gcp_service_account: full GCP service-account JSON
  - SPREADSHEET_ID: the Google Sheet ID
"""

import re
from datetime import datetime, timedelta

import gspread
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from google.oauth2.service_account import Credentials

# ─── Config ──────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Calyx Activity Hub",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]

# Tabs in the Google Sheet and where headers live
SHEET_TABS = {
    "deals":    {"name": "Deals",    "header_row": 2},
    "meetings": {"name": "Meetings", "header_row": 2},
    "calls":    {"name": "Calls",    "header_row": 2},
    "emails":   {"name": "Emails",   "header_row": 2},
    "tickets":  {"name": "Tickets",  "header_row": 2},
}

REPS = [
    "Brad Sherman",
    "Lance Mitton",
    "Dave Borkowski",
    "Jake Lynch",
    "Alex Gonzalez",
    "Owen Labombard",
]

PIPELINES = [
    "Growth Pipeline (Upsell/Cross-sell)",
    "Acquisition (New Customer)",
    "Retention (Existing Product)",
    "Calyx Distribution",
]

# HubSpot User ID -> Rep Name (for owner resolution)
UID_TO_NAME = {
    "56564763":  "Alex Gonzalez",
    "56562506":  "Brad Sherman",
    "119721604": "Dave Borkowski",
    "56564944":  "Jake Lynch",
    "79617483":  "Lance Mitton",
    "85412002":  "Owen Labombard",
}

# ─── Helpers ─────────────────────────────────────────────────────────────────


def to_snake(name: str) -> str:
    """Convert a column header to snake_case."""
    s = re.sub(r"[\s\-\.\/\(\)]+", "_", str(name).strip())
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s)
    return re.sub(r"_+", "_", s).lower().strip("_")


COLUMN_ALIASES = {
    "create_date": "created_date",
    "associated_company_name": "company_name",
    "opp_owner": "hubspot_owner_name",
    "activity_assigned_to": "activity_assigned_to",
    "first_name_activity_assigned_to": "owner_first_name",
    "last_name_activity_assigned_to": "owner_last_name",
    "created_by_user_id": "created_by_user_id",
    "updated_by_user_id": "updated_by_user_id",
    "number_of_email_opens": "email_opens",
    "number_of_email_clicks": "email_clicks",
    "number_of_email_replies": "email_replies",
    "first_name_ticket_owner": "ticket_owner_first_name",
    "object_create_date_time": "created_date",
}

DATE_COLUMNS = {
    "created_date", "close_date", "activity_date", "meeting_start_time",
    "meeting_end_time", "last_modified_date",
}


def normalize_df(df: pd.DataFrame) -> pd.DataFrame:
    """Snake-case columns, apply aliases, coerce dates."""
    df = df.copy()
    df.columns = [to_snake(c) for c in df.columns]
    df.rename(columns={k: v for k, v in COLUMN_ALIASES.items() if k in df.columns}, inplace=True)
    for col in DATE_COLUMNS & set(df.columns):
        df[col] = pd.to_datetime(df[col], errors="coerce")
    return df


def resolve_owner(df: pd.DataFrame) -> pd.DataFrame:
    """Try to fill hubspot_owner_name from first/last name cols or UID map."""
    df = df.copy()
    if "hubspot_owner_name" not in df.columns:
        # Build from first + last name
        if "owner_first_name" in df.columns and "owner_last_name" in df.columns:
            df["hubspot_owner_name"] = (
                df["owner_first_name"].fillna("").str.strip()
                + " "
                + df["owner_last_name"].fillna("").str.strip()
            ).str.strip()
        # Or from UID
        elif "activity_assigned_to" in df.columns:
            df["hubspot_owner_name"] = (
                df["activity_assigned_to"]
                .astype(str)
                .str.replace(r"\.0$", "", regex=True)
                .map(UID_TO_NAME)
            )
        elif "created_by_user_id" in df.columns:
            df["hubspot_owner_name"] = (
                df["created_by_user_id"]
                .astype(str)
                .str.replace(r"\.0$", "", regex=True)
                .map(UID_TO_NAME)
            )
    return df


# ─── Google Sheets ───────────────────────────────────────────────────────────


@st.cache_data(ttl=600, show_spinner="Loading data from Google Sheets...")
def load_data() -> dict[str, pd.DataFrame]:
    """Read all tabs from the Google Sheet and return normalized DataFrames."""
    creds = Credentials.from_service_account_info(
        dict(st.secrets["gcp_service_account"]), scopes=SCOPES
    )
    client = gspread.authorize(creds)
    spreadsheet = client.open_by_key(st.secrets["SPREADSHEET_ID"])

    data = {}
    for key, cfg in SHEET_TABS.items():
        try:
            ws = spreadsheet.worksheet(cfg["name"])
        except gspread.exceptions.WorksheetNotFound:
            data[key] = pd.DataFrame()
            continue

        rows = ws.get_all_values()
        header_idx = cfg["header_row"] - 1  # 0-based
        if len(rows) <= header_idx:
            data[key] = pd.DataFrame()
            continue

        headers = rows[header_idx]
        body = rows[header_idx + 1:]
        df = pd.DataFrame(body, columns=headers)
        df = df.loc[:, (df.columns != "") & df.columns.notna()]
        df = df.replace("", pd.NA).dropna(how="all").reset_index(drop=True)
        df = normalize_df(df)
        df = resolve_owner(df)
        data[key] = df

    return data


# ─── Styling ─────────────────────────────────────────────────────────────────

COLORS = {
    "pink": "#f472b6",
    "blue": "#818cf8",
    "purple": "#c084fc",
    "green": "#34d399",
    "red": "#fb7185",
    "cyan": "#67e8f9",
    "amber": "#fbbf24",
}

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');
    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
    .metric-card {
        background: linear-gradient(135deg, #1e1a35 0%, #151228 100%);
        border: 1px solid #2d2750;
        border-radius: 12px;
        padding: 1.2rem;
        text-align: center;
    }
    .metric-value { font-size: 2rem; font-weight: 700; }
    .metric-label { font-size: 0.85rem; color: #a0a0b8; margin-top: 0.3rem; }
</style>
""", unsafe_allow_html=True)


def metric_card(label: str, value, color: str = "#818cf8"):
    st.markdown(
        f"""<div class="metric-card">
            <div class="metric-value" style="color:{color}">{value}</div>
            <div class="metric-label">{label}</div>
        </div>""",
        unsafe_allow_html=True,
    )


# ─── Sidebar Filters ────────────────────────────────────────────────────────

def sidebar_filters(data: dict[str, pd.DataFrame]):
    st.sidebar.markdown("## 📊 Calyx Activity Hub")
    st.sidebar.divider()

    # Date range
    st.sidebar.markdown("### Date Range")
    preset = st.sidebar.selectbox("Quick select", [
        "Last 7 days", "Last 14 days", "Last 30 days",
        "This Quarter", "All Time", "Custom",
    ])
    today = datetime.now().date()
    if preset == "Last 7 days":
        start = today - timedelta(days=7)
        end = today
    elif preset == "Last 14 days":
        start = today - timedelta(days=14)
        end = today
    elif preset == "Last 30 days":
        start = today - timedelta(days=30)
        end = today
    elif preset == "This Quarter":
        q_month = ((today.month - 1) // 3) * 3 + 1
        start = today.replace(month=q_month, day=1)
        end = today
    elif preset == "Custom":
        start = st.sidebar.date_input("Start", today - timedelta(days=30))
        end = st.sidebar.date_input("End", today)
    else:  # All Time
        start = datetime(2020, 1, 1).date()
        end = today

    # Rep filter
    st.sidebar.markdown("### Sales Reps")
    selected_reps = st.sidebar.multiselect("Reps", REPS, default=REPS)

    st.sidebar.divider()
    st.sidebar.caption(f"Last refreshed: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    return pd.Timestamp(start), pd.Timestamp(end), selected_reps


# ─── Filter helpers ──────────────────────────────────────────────────────────

def filter_by_date(df: pd.DataFrame, start, end, date_col: str = "created_date"):
    if df.empty or date_col not in df.columns:
        return df
    mask = (df[date_col] >= start) & (df[date_col] <= end + pd.Timedelta(days=1))
    return df.loc[mask].copy()


def filter_by_rep(df: pd.DataFrame, reps: list[str]):
    if df.empty or "hubspot_owner_name" not in df.columns:
        return df
    return df.loc[df["hubspot_owner_name"].isin(reps)].copy()


# ─── Dashboard Pages ────────────────────────────────────────────────────────

def page_overview(calls, meetings, emails, deals):
    st.markdown("## Overview")

    # KPI row
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        metric_card("Total Calls", len(calls), COLORS["blue"])
    with c2:
        metric_card("Total Meetings", len(meetings), COLORS["pink"])
    with c3:
        metric_card("Total Emails", len(emails), COLORS["purple"])
    with c4:
        active = deals[~deals.get("deal_stage", pd.Series()).isin(
            ["Closed Won", "Closed Lost", "NCR", "Sales Order Created in NS"]
        )] if "deal_stage" in deals.columns else deals
        metric_card("Active Deals", len(active), COLORS["green"])

    st.divider()

    # Activity by rep
    frames = []
    for label, df in [("Calls", calls), ("Meetings", meetings), ("Emails", emails)]:
        if not df.empty and "hubspot_owner_name" in df.columns:
            counts = df.groupby("hubspot_owner_name").size().reset_index(name="count")
            counts["type"] = label
            frames.append(counts)

    if frames:
        combined = pd.concat(frames)
        fig = px.bar(
            combined, x="hubspot_owner_name", y="count", color="type",
            barmode="group", title="Activity by Rep",
            color_discrete_map={"Calls": COLORS["blue"], "Meetings": COLORS["pink"], "Emails": COLORS["purple"]},
        )
        fig.update_layout(
            xaxis_title="", yaxis_title="Count",
            plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
            font_color="#e0e0e0",
        )
        st.plotly_chart(fig, use_container_width=True)

    # Activity over time
    for label, df, color, date_col in [
        ("Calls", calls, COLORS["blue"], "activity_date"),
        ("Meetings", meetings, COLORS["pink"], "meeting_start_time"),
        ("Emails", emails, COLORS["purple"], "created_date"),
    ]:
        dcol = date_col if date_col in df.columns else "created_date"
        if not df.empty and dcol in df.columns:
            daily = df.set_index(dcol).resample("D").size().reset_index(name="count")
            daily.columns = ["date", "count"]
            fig = px.area(daily, x="date", y="count", title=f"{label} per Day", color_discrete_sequence=[color])
            fig.update_layout(
                plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                font_color="#e0e0e0", xaxis_title="", yaxis_title="",
            )
            st.plotly_chart(fig, use_container_width=True)


def page_calls(calls):
    st.markdown("## Calls")
    if calls.empty:
        st.info("No call data for this period.")
        return

    c1, c2 = st.columns(2)
    with c1:
        metric_card("Total Calls", len(calls), COLORS["blue"])
    with c2:
        if "call_direction" in calls.columns:
            outbound = calls["call_direction"].str.contains("outbound", case=False, na=False).sum()
            metric_card("Outbound", outbound, COLORS["cyan"])

    if "hubspot_owner_name" in calls.columns:
        by_rep = calls["hubspot_owner_name"].value_counts().reset_index()
        by_rep.columns = ["rep", "calls"]
        fig = px.bar(by_rep, x="rep", y="calls", title="Calls by Rep", color_discrete_sequence=[COLORS["blue"]])
        fig.update_layout(plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", font_color="#e0e0e0")
        st.plotly_chart(fig, use_container_width=True)

    st.dataframe(calls, use_container_width=True)


def page_meetings(meetings):
    st.markdown("## Meetings")
    if meetings.empty:
        st.info("No meeting data for this period.")
        return

    metric_card("Total Meetings", len(meetings), COLORS["pink"])

    if "hubspot_owner_name" in meetings.columns:
        by_rep = meetings["hubspot_owner_name"].value_counts().reset_index()
        by_rep.columns = ["rep", "meetings"]
        fig = px.bar(by_rep, x="rep", y="meetings", title="Meetings by Rep", color_discrete_sequence=[COLORS["pink"]])
        fig.update_layout(plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", font_color="#e0e0e0")
        st.plotly_chart(fig, use_container_width=True)

    st.dataframe(meetings, use_container_width=True)


def page_emails(emails):
    st.markdown("## Emails")
    if emails.empty:
        st.info("No email data for this period.")
        return

    c1, c2 = st.columns(2)
    with c1:
        metric_card("Total Emails", len(emails), COLORS["purple"])
    with c2:
        if "email_opens" in emails.columns:
            emails["email_opens"] = pd.to_numeric(emails["email_opens"], errors="coerce")
            total_opens = int(emails["email_opens"].sum())
            metric_card("Total Opens", total_opens, COLORS["amber"])

    if "hubspot_owner_name" in emails.columns:
        by_rep = emails["hubspot_owner_name"].value_counts().reset_index()
        by_rep.columns = ["rep", "emails"]
        fig = px.bar(by_rep, x="rep", y="emails", title="Emails by Rep", color_discrete_sequence=[COLORS["purple"]])
        fig.update_layout(plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", font_color="#e0e0e0")
        st.plotly_chart(fig, use_container_width=True)

    st.dataframe(emails, use_container_width=True)


def page_deals(deals):
    st.markdown("## Deals")
    if deals.empty:
        st.info("No deal data for this period.")
        return

    if "deal_stage" in deals.columns:
        active = deals[~deals["deal_stage"].isin(["Closed Won", "Closed Lost", "NCR", "Sales Order Created in NS"])]
        won = deals[deals["deal_stage"] == "Closed Won"]
        lost = deals[deals["deal_stage"] == "Closed Lost"]

        c1, c2, c3 = st.columns(3)
        with c1:
            metric_card("Active Deals", len(active), COLORS["cyan"])
        with c2:
            metric_card("Closed Won", len(won), COLORS["green"])
        with c3:
            metric_card("Closed Lost", len(lost), COLORS["red"])

        # Pipeline chart
        stage_counts = deals["deal_stage"].value_counts().reset_index()
        stage_counts.columns = ["stage", "count"]
        fig = px.bar(stage_counts, x="stage", y="count", title="Deals by Stage", color_discrete_sequence=[COLORS["cyan"]])
        fig.update_layout(plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", font_color="#e0e0e0")
        st.plotly_chart(fig, use_container_width=True)

    if "pipeline" in deals.columns:
        pipe_counts = deals["pipeline"].value_counts().reset_index()
        pipe_counts.columns = ["pipeline", "count"]
        fig = px.pie(pipe_counts, names="pipeline", values="count", title="Deals by Pipeline",
                     color_discrete_sequence=[COLORS["blue"], COLORS["pink"], COLORS["green"], COLORS["amber"]])
        fig.update_layout(plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", font_color="#e0e0e0")
        st.plotly_chart(fig, use_container_width=True)

    st.dataframe(deals, use_container_width=True)


def page_tickets(tickets):
    st.markdown("## Tickets")
    if tickets.empty:
        st.info("No ticket data for this period.")
        return

    metric_card("Total Tickets", len(tickets), COLORS["amber"])
    st.dataframe(tickets, use_container_width=True)


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    data = load_data()

    start, end, reps = sidebar_filters(data)

    # Apply filters
    filtered = {}
    for key, df in data.items():
        fdf = filter_by_rep(df, reps)
        # Pick the best date column for filtering
        if "meeting_start_time" in fdf.columns:
            fdf = filter_by_date(fdf, start, end, "meeting_start_time")
        elif "activity_date" in fdf.columns:
            fdf = filter_by_date(fdf, start, end, "activity_date")
        elif "created_date" in fdf.columns:
            fdf = filter_by_date(fdf, start, end, "created_date")
        filtered[key] = fdf

    calls = filtered.get("calls", pd.DataFrame())
    meetings = filtered.get("meetings", pd.DataFrame())
    emails = filtered.get("emails", pd.DataFrame())
    deals = filtered.get("deals", pd.DataFrame())
    tickets = filtered.get("tickets", pd.DataFrame())

    # Navigation
    tab = st.sidebar.radio(
        "Navigate",
        ["Overview", "Calls", "Meetings", "Emails", "Deals", "Tickets"],
        label_visibility="collapsed",
    )

    if tab == "Overview":
        page_overview(calls, meetings, emails, deals)
    elif tab == "Calls":
        page_calls(calls)
    elif tab == "Meetings":
        page_meetings(meetings)
    elif tab == "Emails":
        page_emails(emails)
    elif tab == "Deals":
        page_deals(deals)
    elif tab == "Tickets":
        page_tickets(tickets)


if __name__ == "__main__":
    main()
