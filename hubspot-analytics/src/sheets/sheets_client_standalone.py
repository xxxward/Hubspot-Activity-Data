"""
Standalone Google Sheets client for scheduled jobs (no Streamlit dependency).

Reads credentials from environment variables instead of st.secrets.
"""

import json
import logging
import os

import gspread
import pandas as pd
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
    "notes": "Notes",
    "new_pipeline": "New Pipeline",
    "gong_ai_summaries": "Gong AI Summaries",
    "gong_calls": "Gong Calls",
    "gong_users": "Gong Users",
}

# Tabs created by Google Apps Script (not Coefficient) have headers in row 1
_GONG_TABS = {"Gong AI Summaries", "Gong Calls", "Gong Users", "Sync Log"}


def _build_client() -> gspread.Client:
    """Build gspread client from env var GCP_SERVICE_ACCOUNT_JSON."""
    sa_json = os.environ.get("GCP_SERVICE_ACCOUNT_JSON", "")
    if not sa_json:
        # Fall back to file path
        sa_path = os.environ.get("GCP_SERVICE_ACCOUNT_FILE", "service-account.json")
        with open(sa_path) as f:
            sa_info = json.load(f)
    else:
        sa_info = json.loads(sa_json)

    creds = Credentials.from_service_account_info(sa_info, scopes=SCOPES)
    client = gspread.authorize(creds)
    logger.info("Authenticated with Google Sheets (standalone).")
    return client


def _read_tab(spreadsheet: gspread.Spreadsheet, tab_name: str) -> pd.DataFrame:
    """Read one worksheet tab into a DataFrame.

    Coefficient tabs: headers in row 2 (row 1 is metadata/blank).
    Gong tabs (Apps Script): headers in row 1.
    """
    try:
        ws = spreadsheet.worksheet(tab_name)
    except gspread.exceptions.WorksheetNotFound:
        logger.warning("Tab '%s' not found - returning empty DataFrame.", tab_name)
        return pd.DataFrame()

    all_values = ws.get_all_values()

    is_gong_tab = tab_name in _GONG_TABS

    if is_gong_tab:
        if len(all_values) < 2:
            logger.warning("Tab '%s' has fewer than 2 rows - returning empty DataFrame.", tab_name)
            return pd.DataFrame()
        headers = all_values[0]
        data_rows = all_values[1:]
    else:
        if len(all_values) < 3:
            logger.warning("Tab '%s' has fewer than 3 rows - returning empty DataFrame.", tab_name)
            return pd.DataFrame()
        headers = all_values[1]
        data_rows = all_values[2:]

    df = pd.DataFrame(data_rows, columns=headers)
    df = df.loc[:, df.columns != ""]
    df = df.loc[:, df.columns.notna()]
    df = df.replace("", pd.NA).dropna(how="all").reset_index(drop=True)
    logger.info("Read %d rows x %d cols from '%s'.", len(df), len(df.columns), tab_name)
    return df


def read_all_tabs_standalone() -> dict[str, pd.DataFrame]:
    """Read every configured tab without Streamlit."""
    client = _build_client()
    sid = os.environ.get("SPREADSHEET_ID", "")
    if not sid:
        raise EnvironmentError("SPREADSHEET_ID environment variable not set.")
    spreadsheet = client.open_by_key(sid)
    logger.info("Opened spreadsheet: %s", spreadsheet.title)

    data: dict[str, pd.DataFrame] = {}
    for key, tab_name in DEFAULT_TABS.items():
        data[key] = _read_tab(spreadsheet, tab_name)
    return data
