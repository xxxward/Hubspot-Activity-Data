"""
Business-rule filters: rep scope, pipeline scope, terminal-stage tagging.

All filtering is done in-memory on normalized DataFrames.
"""

import logging

import pandas as pd
import numpy as np

from src.parsing.normalize import safe_column

logger = logging.getLogger(__name__)

# ── Constants ───────────────────────────────────────────────────────

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


# ── Rep filter ──────────────────────────────────────────────────────

def filter_by_rep(
    df: pd.DataFrame,
    owner_col: str = "hubspot_owner_name",
    reps: list[str] | None = None,
) -> pd.DataFrame:
    """Keep only rows belonging to in-scope reps."""
    if df.empty:
        return df
    reps = reps or REPS_IN_SCOPE
    col = safe_column(df, owner_col)
    mask = col.isin(reps)
    out = df.loc[mask].copy()
    logger.info("Rep filter (%s): %d → %d rows.", owner_col, len(df), len(out))
    return out


# ── Pipeline filter ─────────────────────────────────────────────────

def filter_by_pipeline(
    df: pd.DataFrame,
    pipeline_col: str = "pipeline",
    pipelines: list[str] | None = None,
) -> pd.DataFrame:
    """Keep only rows in in-scope pipelines."""
    if df.empty:
        return df
    if pipeline_col not in df.columns:
        logger.warning("Column '%s' not found — skipping pipeline filter.", pipeline_col)
        return df
    pipelines = pipelines or PIPELINES_IN_SCOPE
    mask = df[pipeline_col].isin(pipelines)
    out = df.loc[mask].copy()
    logger.info("Pipeline filter: %d → %d rows.", len(df), len(out))
    return out


# ── Terminal tagging ────────────────────────────────────────────────

def tag_terminal_stages(df: pd.DataFrame, stage_col: str = "deal_stage") -> pd.DataFrame:
    """
    Add:
      is_terminal  (bool)   — True if deal is in a terminal stage
      terminal_status (str)  — CLOSED_WON | CLOSED_LOST | NCR | SALES_ORDER_CREATED | NaN
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


# ── Composite filter pipelines ──────────────────────────────────────

def apply_deal_filters(df: pd.DataFrame) -> pd.DataFrame:
    """Full deal filtering: rep → pipeline → terminal tagging."""
    df = filter_by_rep(df)
    df = filter_by_pipeline(df)
    df = tag_terminal_stages(df)
    return df


def apply_activity_filters(df: pd.DataFrame) -> pd.DataFrame:
    """Filter activity rows (calls, meetings, tasks) to in-scope reps only."""
    return filter_by_rep(df)
