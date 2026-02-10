"""
Terminal deal metrics: closed won vs lost by rep, NCR counts,
Sales Order Created counts, average sales cycle length.
"""

import logging

import pandas as pd

from src.parsing.filters import get_terminal_deals
from src.utils.dates import sales_cycle_days

logger = logging.getLogger(__name__)


def closed_won_vs_lost_by_rep(deals: pd.DataFrame) -> pd.DataFrame:
    """Closed won and closed lost counts by rep.  Returns: rep | closed_won | closed_lost | net"""
    terminal = get_terminal_deals(deals)
    if terminal.empty:
        return pd.DataFrame(columns=["hubspot_owner_name", "closed_won", "closed_lost", "net"])

    owner = "hubspot_owner_name"
    if owner not in terminal.columns:
        return pd.DataFrame()

    won = (terminal.loc[terminal["terminal_status"] == "CLOSED_WON"]
           .groupby(owner).size().reset_index(name="closed_won"))
    lost = (terminal.loc[terminal["terminal_status"] == "CLOSED_LOST"]
            .groupby(owner).size().reset_index(name="closed_lost"))

    result = pd.merge(won, lost, on=owner, how="outer").fillna(0)
    for c in ("closed_won", "closed_lost"):
        result[c] = result[c].astype(int)
    result["net"] = result["closed_won"] - result["closed_lost"]
    return result


def ncr_count_by_pipeline(deals: pd.DataFrame) -> pd.DataFrame:
    terminal = get_terminal_deals(deals)
    ncr = terminal.loc[terminal.get("terminal_status", pd.Series()) == "NCR"]
    if ncr.empty:
        return pd.DataFrame(columns=["pipeline", "ncr_count"])
    return ncr.groupby("pipeline", dropna=False).size().reset_index(name="ncr_count")


def sales_order_created_count(deals: pd.DataFrame) -> pd.DataFrame:
    terminal = get_terminal_deals(deals)
    so = terminal.loc[terminal.get("terminal_status", pd.Series()) == "SALES_ORDER_CREATED"]
    if so.empty:
        return pd.DataFrame(columns=["pipeline", "hubspot_owner_name", "so_count"])
    group = [c for c in ("pipeline", "hubspot_owner_name") if c in so.columns]
    return so.groupby(group, dropna=False).size().reset_index(name="so_count")


def avg_sales_cycle_length(deals: pd.DataFrame) -> pd.DataFrame:
    """
    Average sales cycle (created → closed) in days for terminal deals.

    Returns: rep | pipeline | avg_cycle_days | median_cycle_days | deal_count
    """
    terminal = get_terminal_deals(deals)
    if terminal.empty:
        return pd.DataFrame(columns=["hubspot_owner_name", "pipeline",
                                      "avg_cycle_days", "median_cycle_days", "deal_count"])

    created_col = next((c for c in ("created_date", "create_date") if c in terminal.columns), None)
    closed_col = next((c for c in ("close_date", "closedate") if c in terminal.columns), None)

    if not created_col or not closed_col:
        logger.warning("Cannot compute cycle length — missing date columns.")
        return pd.DataFrame()

    terminal = terminal.copy()
    terminal["cycle_days"] = sales_cycle_days(terminal[created_col], terminal[closed_col])
    terminal = terminal.loc[terminal["cycle_days"].notna() & (terminal["cycle_days"] >= 0)]

    group = [c for c in ("hubspot_owner_name", "pipeline") if c in terminal.columns]
    if not group:
        return pd.DataFrame()

    result = (
        terminal.groupby(group, dropna=False)["cycle_days"]
        .agg(["mean", "median", "size"])
        .reset_index()
    )
    result.columns = group + ["avg_cycle_days", "median_cycle_days", "deal_count"]
    result["avg_cycle_days"] = result["avg_cycle_days"].round(1)
    result["median_cycle_days"] = result["median_cycle_days"].round(1)
    return result


def terminal_summary(deals: pd.DataFrame) -> dict[str, pd.DataFrame]:
    return {
        "closed_won_vs_lost": closed_won_vs_lost_by_rep(deals),
        "ncr_by_pipeline": ncr_count_by_pipeline(deals),
        "sales_order_created": sales_order_created_count(deals),
        "avg_sales_cycle": avg_sales_cycle_length(deals),
    }
