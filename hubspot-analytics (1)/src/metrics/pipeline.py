"""
Pipeline metrics: active pipeline value, deals closing this quarter,
deal count by stage, average days in stage, win rate.
"""

import logging

import pandas as pd
import numpy as np

from src.parsing.filters import get_active_deals, WIN_STAGES
from src.parsing.normalize import safe_column
from src.utils.dates import current_quarter_range

logger = logging.getLogger(__name__)


def active_pipeline_value(deals: pd.DataFrame) -> pd.DataFrame:
    """Active pipeline value by pipeline.  Returns: pipeline | deal_count | total_value | avg_value"""
    active = get_active_deals(deals)
    if active.empty:
        return pd.DataFrame(columns=["pipeline", "deal_count", "total_value", "avg_value"])
    active = active.assign(amount=safe_column(active, "amount").fillna(0))
    return (
        active.groupby("pipeline", dropna=False)
        .agg(deal_count=("amount", "size"),
             total_value=("amount", "sum"),
             avg_value=("amount", "mean"))
        .reset_index()
    )


def deals_closing_this_quarter(deals: pd.DataFrame) -> pd.DataFrame:
    """Active deals with close_date in the current calendar quarter."""
    active = get_active_deals(deals)
    if active.empty or "close_date" not in active.columns:
        return pd.DataFrame()
    q_start, q_end = current_quarter_range()
    close = pd.to_datetime(active["close_date"], errors="coerce")
    return active.loc[(close >= q_start) & (close <= q_end)].copy()


def deal_count_by_stage(deals: pd.DataFrame) -> pd.DataFrame:
    """Deal count in each stage (including terminal).  Returns: deal_stage | count | is_terminal"""
    if deals.empty or "deal_stage" not in deals.columns:
        return pd.DataFrame(columns=["deal_stage", "count", "is_terminal"])
    return (
        deals.groupby(["deal_stage", "is_terminal"], dropna=False)
        .size()
        .reset_index(name="count")
        .sort_values("count", ascending=False)
    )


def avg_days_in_stage(deals: pd.DataFrame) -> pd.DataFrame:
    """
    Estimated average days deals have spent in their current stage.

    Uses last_modified_date as a proxy (no stage-change history available).
    Falls back to created_date if last_modified_date is missing.
    """
    if deals.empty:
        return pd.DataFrame(columns=["deal_stage", "avg_days"])
    df = deals.copy()
    now = pd.Timestamp.now()
    if "last_modified_date" in df.columns:
        ref = pd.to_datetime(df["last_modified_date"], errors="coerce")
    elif "created_date" in df.columns:
        ref = pd.to_datetime(df["created_date"], errors="coerce")
    else:
        df["days_in_stage"] = np.nan
        ref = None

    if ref is not None:
        df["days_in_stage"] = (now - ref).dt.days

    result = (
        df.groupby("deal_stage", dropna=False)["days_in_stage"]
        .mean()
        .reset_index(name="avg_days")
        .sort_values("avg_days", ascending=False)
    )
    result["avg_days"] = result["avg_days"].round(1)
    return result


def win_rate(deals: pd.DataFrame) -> pd.DataFrame:
    """
    Win rate by pipeline × rep.

    Win  = Closed Won or Sales Order Created in NS
    Denom = all terminal deals
    """
    if deals.empty or "is_terminal" not in deals.columns:
        return pd.DataFrame(columns=["pipeline", "hubspot_owner_name",
                                      "wins", "terminal_count", "win_rate"])
    terminal = deals.loc[deals["is_terminal"]].copy()
    if terminal.empty:
        return pd.DataFrame(columns=["pipeline", "hubspot_owner_name",
                                      "wins", "terminal_count", "win_rate"])
    terminal["is_won"] = terminal["deal_stage"].isin(WIN_STAGES)

    group = [c for c in ("pipeline", "hubspot_owner_name") if c in terminal.columns]
    if not group:
        return pd.DataFrame()

    result = (
        terminal.groupby(group, dropna=False)
        .agg(wins=("is_won", "sum"), terminal_count=("is_won", "size"))
        .reset_index()
    )
    result["win_rate"] = (result["wins"] / result["terminal_count"]).round(4)
    return result


def pipeline_summary(deals: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Compute all pipeline metrics."""
    return {
        "active_pipeline_value": active_pipeline_value(deals),
        "deals_closing_this_quarter": deals_closing_this_quarter(deals),
        "deal_count_by_stage": deal_count_by_stage(deals),
        "avg_days_in_stage": avg_days_in_stage(deals),
        "win_rate": win_rate(deals),
    }
