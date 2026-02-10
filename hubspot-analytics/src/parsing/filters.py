"""
Business-rule filters: rep scope, pipeline scope, terminal-stage tagging.

All filtering is done in-memory on normalized DataFrames.

IMPORTANT: Different tabs use different column names for the rep/owner:
  - Deals:    hubspot_owner_name (mapped from "Opp Owner")
  - Meetings: hubspot_owner_name (mapped from "Activity assigned to")
  - Calls:    hubspot_owner_name (mapped from "Activity assigned to")
  - Tasks:    full_name (no "Activity assigned to" column)

The filter logic checks multiple candidate columns.
"""

import logging

import pandas as pd
import numpy as np

from src.parsing.normalize import safe_column

logger = logging.getLogger(__name__)

# -- Constants ---------------------------------------------------------------

REPS_IN_SCOPE: list[str] = [
    "Brad Sherman",
    "Lance Mitton",
    "Dave Borkowski",
    "Jake Lynch",
    "Alex Gonzalez",
    "Owen Labombard",
]

PIPELINES_IN_SCOPE: list[str] = [
    "Growth Pipeline (Upsell/Cross-sell)",
    "Acquisition (New Customer)",
    "Retention (Existing Product)",
    "Calyx Distribution",
]

TERMINAL_STAGES: dict[str, str] = {
    "Closed Won": "CLOSED_WON",
    "Closed Lost": "CLOSED_LOST",
    "NCR": "NCR",
    "Sales Order Created in NS": "SALES_ORDER_CREATED",
}

WIN_STAGES: set[str] = {"Closed Won", "Sales Order Created in NS"}

# Candidate columns that might contain the rep/owner name, in priority order
OWNER_CANDIDATES: list[str] = [
    "hubspot_owner_name",
    "activity_assigned_to",
    "full_name",
    "opp_owner",
    "deal_owner",
    "activity_created_by",
]


# -- Owner column resolution -------------------------------------------------

def _find_owner_col(df: pd.DataFrame) -> str | None:
    """Find the best owner/rep column in a DataFrame."""
    for col in OWNER_CANDIDATES:
        if col in df.columns:
            return col
    return None


def _ensure_owner_col(df: pd.DataFrame) -> pd.DataFrame:
    """
    Ensure the DataFrame has a 'hubspot_owner_name' column.

    If it doesn't exist but another owner candidate does, copy it over.
    This normalizes all tabs to use the same column name for filtering.
    """
    if df.empty:
        return df
    if "hubspot_owner_name" in df.columns:
        return df

    df = df.copy()
    source_col = _find_owner_col(df)
    if source_col:
        df["hubspot_owner_name"] = df[source_col]
        logger.info("Mapped '%s' -> 'hubspot_owner_name' for rep filtering.", source_col)
    else:
        logger.warning("No owner column found. Available columns: %s", list(df.columns))
    return df


# -- Rep filter ---------------------------------------------------------------

def filter_by_rep(
    df: pd.DataFrame,
    reps: list[str] | None = None,
) -> pd.DataFrame:
    """Keep only rows belonging to in-scope reps."""
    if df.empty:
        return df
    df = _ensure_owner_col(df)
    reps = reps or REPS_IN_SCOPE
    col = safe_column(df, "hubspot_owner_name")
    mask = col.isin(reps)
    out = df.loc[mask].copy()
    logger.info("Rep filter: %d -> %d rows.", len(df), len(out))
    return out


# -- Pipeline filter ----------------------------------------------------------

def filter_by_pipeline(
    df: pd.DataFrame,
    pipeline_col: str = "pipeline",
    pipelines: list[str] | None = None,
) -> pd.DataFrame:
    """Keep only rows in in-scope pipelines."""
    if df.empty:
        return df
    if pipeline_col not in df.columns:
        logger.warning("Column '%s' not found - skipping pipeline filter.", pipeline_col)
        return df
    pipelines = pipelines or PIPELINES_IN_SCOPE
    mask = df[pipeline_col].isin(pipelines)
    out = df.loc[mask].copy()
    logger.info("Pipeline filter: %d -> %d rows.", len(df), len(out))
    return out


# -- Terminal tagging ---------------------------------------------------------

def tag_terminal_stages(df: pd.DataFrame, stage_col: str = "deal_stage") -> pd.DataFrame:
    """
    Add:
      is_terminal  (bool)  - True if deal is in a terminal stage
      terminal_status (str) - CLOSED_WON | CLOSED_LOST | NCR | SALES_ORDER_CREATED | NaN
    """
    if df.empty:
        return df
    df = df.copy()
    stage = safe_column(df, stage_col)
    df["is_terminal"] = stage.isin(TERMINAL_STAGES.keys())
    df["terminal_status"] = stage.map(TERMINAL_STAGES)
    logger.info("Terminal tagging: %d terminal / %d total.",
                df["is_terminal"].sum(), len(df))
    return df


def get_active_deals(df: pd.DataFrame) -> pd.DataFrame:
    if "is_terminal" not in df.columns:
        df = tag_terminal_stages(df)
    return df.loc[~df["is_terminal"]].copy()


def get_terminal_deals(df: pd.DataFrame) -> pd.DataFrame:
    if "is_terminal" not in df.columns:
        df = tag_terminal_stages(df)
    return df.loc[df["is_terminal"]].copy()


# -- Composite filter pipelines -----------------------------------------------

def apply_deal_filters(df: pd.DataFrame) -> pd.DataFrame:
    """Full deal filtering: rep -> pipeline -> terminal tagging."""
    df = filter_by_rep(df)
    df = filter_by_pipeline(df)
    df = tag_terminal_stages(df)
    return df


def apply_activity_filters(df: pd.DataFrame) -> pd.DataFrame:
    """Filter activity rows (calls, meetings, tasks) to in-scope reps only."""
    return filter_by_rep(df)
