"""
Google Sheets client: authenticate via service account and read tabs as DataFrames.

Credentials come from Streamlit secrets (st.secrets["gcp_service_account"]),
which works on Streamlit Cloud and locally via .streamlit/secrets.toml.

No .env file or JSON file on disk required.
"""

import logging

import gspread
import pandas as pd
import streamlit as st
from google.oauth2.service_account import Credentials

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]

DEFAULT_TABS: dict[str, str] = {
    "deals": "Deals",
    "meetings": "Meetings",
    "tasks": "Tasks",
    "tickets": "Tickets",
    "calls": "Calls",
}


def _get_tab_name(key: str) -> str:
    try:
        return st.secrets.get(f"SHEET_TAB_{key.upper()}", DEFAULT_TABS.get(key, key))
    except Exception:
        return DEFAULT_TABS.get(key, key)


def _build_client() -> gspread.Client:
    """
    Build gspread client from Streamlit secrets.

    Expects st.secrets["gcp_service_account"] with the full service-account
    JSON fields (type, project_id, private_key, client_email, etc.).
    """
    try:
        sa_info = st.secrets["gcp_service_account"]
    except KeyError:
        raise EnvironmentError(
            "Streamlit secret 'gcp_service_account' not found. "
            "Add your service account JSON under [gcp_service_account] "
            "in .streamlit/secrets.toml or in Streamlit Cloud app settings."
        )
    creds = Credentials.from_service_account_info(dict(sa_info), scopes=SCOPES)
    client = gspread.authorize(creds)
    logger.info("Authenticated with Google Sheets via st.secrets.")
    return client


def _get_spreadsheet_id() -> str:
    try:
        return st.secrets["SPREADSHEET_ID"]
    except KeyError:
        raise EnvironmentError(
            "Streamlit secret 'SPREADSHEET_ID' not found. "
            "Add SPREADSHEET_ID to your secrets."
        )


def _read_tab(spreadsheet: gspread.Spreadsheet, tab_name: str) -> pd.DataFrame:
    """Read one worksheet tab -> DataFrame. Returns empty DF on failure."""
    try:
        ws = spreadsheet.worksheet(tab_name)
    except gspread.exceptions.WorksheetNotFound:
        logger.warning("Tab '%s' not found - returning empty DataFrame.", tab_name)
        return pd.DataFrame()
    records = ws.get_all_records()
    if not records:
        logger.warning("Tab '%s' is empty.", tab_name)
        return pd.DataFrame()
    df = pd.DataFrame(records)
    logger.info("Read %d rows x %d cols from '%s'.", len(df), len(df.columns), tab_name)
    return df


def read_all_tabs() -> dict[str, pd.DataFrame]:
    """
    Read every configured tab -> {key: raw_dataframe}.
    Keys: deals, meetings, tasks, tickets, calls
    """
    client = _build_client()
    sid = _get_spreadsheet_id()
    spreadsheet = client.open_by_key(sid)
    logger.info("Opened spreadsheet: %s", spreadsheet.title)

    data: dict[str, pd.DataFrame] = {}
    for key in DEFAULT_TABS:
        tab = _get_tab_name(key)
        data[key] = _read_tab(spreadsheet, tab)
    return data
