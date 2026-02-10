"""
Google Sheets client: authenticate via service account and read tabs as DataFrames.

Tabs are read using gspread.  Missing or empty tabs return empty DataFrames
so downstream code never has to worry about None.
"""

import os
import logging
from typing import Optional

import gspread
import pandas as pd
from google.oauth2.service_account import Credentials

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]

# ── Default tab names (match the actual spreadsheet) ────────────────
DEFAULT_TABS: dict[str, str] = {
    "deals": "Deals",
    "meetings": "Meetings",
    "tasks": "Tasks",
    "tickets": "Tickets",
    "calls": "Calls",
}


def _get_tab_name(key: str) -> str:
    """Resolve tab name from env var or default."""
    return os.getenv(f"SHEET_TAB_{key.upper()}", DEFAULT_TABS.get(key, key))


def _build_client(sa_file: Optional[str] = None) -> gspread.Client:
    sa_file = sa_file or os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE")
    if not sa_file:
        raise EnvironmentError("GOOGLE_SERVICE_ACCOUNT_FILE not set.")
    if not os.path.exists(sa_file):
        raise FileNotFoundError(f"Service account file not found: {sa_file}")
    creds = Credentials.from_service_account_file(sa_file, scopes=SCOPES)
    client = gspread.authorize(creds)
    logger.info("Authenticated with Google Sheets.")
    return client


def _read_tab(spreadsheet: gspread.Spreadsheet, tab_name: str) -> pd.DataFrame:
    """Read one worksheet tab → DataFrame.  Returns empty DF on any failure."""
    try:
        ws = spreadsheet.worksheet(tab_name)
    except gspread.exceptions.WorksheetNotFound:
        logger.warning("Tab '%s' not found — returning empty DataFrame.", tab_name)
        return pd.DataFrame()
    records = ws.get_all_records()
    if not records:
        logger.warning("Tab '%s' is empty.", tab_name)
        return pd.DataFrame()
    df = pd.DataFrame(records)
    logger.info("Read %d rows × %d cols from '%s'.", len(df), len(df.columns), tab_name)
    return df


def read_all_tabs(
    service_account_file: Optional[str] = None,
    spreadsheet_id: Optional[str] = None,
) -> dict[str, pd.DataFrame]:
    """
    Read every configured tab and return {key: raw_dataframe}.

    Keys: deals, meetings, tasks, tickets, calls
    """
    client = _build_client(service_account_file)
    sid = spreadsheet_id or os.getenv("SPREADSHEET_ID")
    if not sid:
        raise EnvironmentError("SPREADSHEET_ID not set.")
    spreadsheet = client.open_by_key(sid)
    logger.info("Opened spreadsheet: %s", spreadsheet.title)

    data: dict[str, pd.DataFrame] = {}
    for key in DEFAULT_TABS:
        tab = _get_tab_name(key)
        data[key] = _read_tab(spreadsheet, tab)
    return data
