"""
Google Sheets client: authenticate via service account and read tabs as DataFrames.

Credentials come from Streamlit secrets (st.secrets["gcp_service_account"]).

NOTE: Coefficient puts headers in row 2 (row 1 is metadata/blank).
We read all values, skip row 1, and use row 2 as headers.
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
    "emails": "Emails",
}


def _get_tab_name(key: str) -> str:
    try:
        return st.secrets.get(f"SHEET_TAB_{key.upper()}", DEFAULT_TABS.get(key, key))
    except Exception:
        return DEFAULT_TABS.get(key, key)


def _build_client() -> gspread.Client:
    try:
        sa_info = st.secrets["gcp_service_account"]
    except KeyError:
        raise EnvironmentError(
            "Streamlit secret 'gcp_service_account' not found."
        )
    creds = Credentials.from_service_account_info(dict(sa_info), scopes=SCOPES)
    client = gspread.authorize(creds)
    logger.info("Authenticated with Google Sheets via st.secrets.")
    return client


def _get_spreadsheet_id() -> str:
    try:
        return st.secrets["SPREADSHEET_ID"]
    except KeyError:
        raise EnvironmentError("Streamlit secret 'SPREADSHEET_ID' not found.")


def _read_tab(spreadsheet: gspread.Spreadsheet, tab_name: str) -> pd.DataFrame:
    """
    Read one worksheet tab into a DataFrame.

    Coefficient places headers in row 2, so we:
      1. get_all_values() to grab the raw grid
      2. Use row index 1 (second row) as column headers
      3. Data starts from row index 2 onward
      4. Drop any columns with blank headers
    """
    try:
        ws = spreadsheet.worksheet(tab_name)
    except gspread.exceptions.WorksheetNotFound:
        logger.warning("Tab '%s' not found - returning empty DataFrame.", tab_name)
        return pd.DataFrame()

    all_values = ws.get_all_values()
    if len(all_values) < 3:
        # Need at least: row 0 (Coefficient meta), row 1 (headers), row 2+ (data)
        logger.warning("Tab '%s' has fewer than 3 rows - returning empty DataFrame.", tab_name)
        return pd.DataFrame()

    # Row 1 = headers (index 1), rows 2+ = data
    headers = all_values[1]
    data_rows = all_values[2:]

    df = pd.DataFrame(data_rows, columns=headers)

    # Drop columns with blank/empty headers (Coefficient trailing blanks)
    df = df.loc[:, df.columns != ""]
    df = df.loc[:, df.columns.notna()]

    # Drop fully empty rows
    df = df.replace("", pd.NA).dropna(how="all").reset_index(drop=True)

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
