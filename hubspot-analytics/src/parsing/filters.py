"""
Business-rule filters: rep scope, pipeline scope, terminal-stage tagging.
"""

import logging

import pandas as pd
import numpy as np

from src.parsing.normalize import safe_column

logger = logging.getLogger(__name__)

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


def filter_by_rep(df: pd.DataFrame, reps: list[str] | None = None) -> pd.DataFrame:
    """Keep only rows where hubspot_owner_name is in scope."""
    if df.empty or "hubspot_owner_name" not in df.columns:
        return df
    reps = reps or REPS_IN_SCOPE
    out = df.loc[df["hubspot_owner_name"].isin(reps)].copy()
    logger.info("Rep filter: %d -> %d rows.", len(df), len(out))
    return out


def filter_by_pipeline(df: pd.DataFrame, pipelines: list[str] | None = None) -> pd.DataFrame:
    if df.empty or "pipeline" not in df.columns:
        return df
    pipelines = pipelines or PIPELINES_IN_SCOPE
    out = df.loc[df["pipeline"].isin(pipelines)].copy()
    logger.info("Pipeline filter: %d -> %d rows.", len(df), len(out))
    return out


def tag_terminal_stages(df: pd.DataFrame, stage_col: str = "deal_stage") -> pd.DataFrame:
    if df.empty:
        return df
    df = df.copy()
    stage = safe_column(df, stage_col)
    df["is_terminal"] = stage.isin(TERMINAL_STAGES.keys())
    df["terminal_status"] = stage.map(TERMINAL_STAGES)
    logger.info("Terminal tagging: %d terminal / %d total.", df["is_terminal"].sum(), len(df))
    return df


def get_active_deals(df: pd.DataFrame) -> pd.DataFrame:
    if "is_terminal" not in df.columns:
        df = tag_terminal_stages(df)
    return df.loc[~df["is_terminal"]].copy()


def get_terminal_deals(df: pd.DataFrame) -> pd.DataFrame:
    if "is_terminal" not in df.columns:
        df = tag_terminal_stages(df)
    return df.loc[df["is_terminal"]].copy()


def apply_deal_filters(df: pd.DataFrame) -> pd.DataFrame:
    df = filter_by_rep(df)
    df = filter_by_pipeline(df)
    df = tag_terminal_stages(df)
    return df


def apply_activity_filters(df: pd.DataFrame) -> pd.DataFrame:
    return filter_by_rep(df)
