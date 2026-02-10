"""
Main orchestrator: load -> normalize -> owner map -> dedup -> filter -> metrics.
"""

import logging
from dataclasses import dataclass, field

import pandas as pd

from src.utils.logging import setup_logging
from src.sheets.sheets_client import read_all_tabs
from src.parsing.normalize import (
    normalize_dataframe, build_uid_map_from_meetings,
    apply_owner_mapping, deduplicate_meetings,
)
from src.parsing.filters import apply_deal_filters, apply_activity_filters
from src.metrics.activity import count_activities, build_combined_activity_log
from src.metrics.pipeline import pipeline_summary
from src.metrics.terminal import terminal_summary
from src.metrics.scoring import compute_activity_score, compute_activity_score_by_period

logger = logging.getLogger(__name__)


@dataclass
class AnalyticsData:
    """Container for every computed DataFrame."""
    # Filtered base tables
    deals: pd.DataFrame = field(default_factory=pd.DataFrame)
    meetings: pd.DataFrame = field(default_factory=pd.DataFrame)
    tasks: pd.DataFrame = field(default_factory=pd.DataFrame)
    tickets: pd.DataFrame = field(default_factory=pd.DataFrame)
    calls: pd.DataFrame = field(default_factory=pd.DataFrame)
    emails: pd.DataFrame = field(default_factory=pd.DataFrame)
    notes: pd.DataFrame = field(default_factory=pd.DataFrame)

    # Activity counts
    activity_counts_daily: pd.DataFrame = field(default_factory=pd.DataFrame)
    activity_counts_weekly: pd.DataFrame = field(default_factory=pd.DataFrame)
    activity_counts_monthly: pd.DataFrame = field(default_factory=pd.DataFrame)
    activity_log: pd.DataFrame = field(default_factory=pd.DataFrame)

    # Scores
    rep_activity_score: pd.DataFrame = field(default_factory=pd.DataFrame)
    rep_activity_score_trend: pd.DataFrame = field(default_factory=pd.DataFrame)

    # Pipeline
    active_pipeline_value: pd.DataFrame = field(default_factory=pd.DataFrame)
    deals_closing_this_quarter: pd.DataFrame = field(default_factory=pd.DataFrame)
    deal_count_by_stage: pd.DataFrame = field(default_factory=pd.DataFrame)
    avg_days_in_stage: pd.DataFrame = field(default_factory=pd.DataFrame)
    win_rate: pd.DataFrame = field(default_factory=pd.DataFrame)

    # Terminal
    closed_won_vs_lost: pd.DataFrame = field(default_factory=pd.DataFrame)
    ncr_by_pipeline: pd.DataFrame = field(default_factory=pd.DataFrame)
    sales_order_created: pd.DataFrame = field(default_factory=pd.DataFrame)
    avg_sales_cycle: pd.DataFrame = field(default_factory=pd.DataFrame)


def load_all() -> AnalyticsData:
    """
    Full pipeline:
      1. Read tabs from Google Sheets
      2. Normalize columns & types
      3. Build UID->Name map from Meetings
      4. Apply owner mapping per tab
      5. Deduplicate meetings
      6. Filter by rep/pipeline/stage
      7. Compute all metrics
    """
    # 1 - Read
    logger.info("Reading Google Sheets...")
    raw = read_all_tabs()

    # 2 - Normalize columns & types
    logger.info("Normalizing...")
    norm = {k: normalize_dataframe(v) for k, v in raw.items()}

    # 3 - Build UID map from meetings (the Rosetta Stone)
    logger.info("Building HubSpot UID -> Name mapping...")
    uid_map = build_uid_map_from_meetings(norm.get("meetings", pd.DataFrame()))

    # 4 - Apply owner mapping per tab type
    logger.info("Applying owner mappings...")
    for tab_type in ("deals", "meetings", "calls", "tasks", "tickets", "emails", "notes"):
        if tab_type in norm and not norm[tab_type].empty:
            norm[tab_type] = apply_owner_mapping(norm[tab_type], uid_map, tab_type)

    # 5 - Deduplicate meetings
    logger.info("Deduplicating meetings...")
    if not norm.get("meetings", pd.DataFrame()).empty:
        norm["meetings"] = deduplicate_meetings(norm["meetings"])

    # 6 - Filter
    logger.info("Filtering...")
    deals = apply_deal_filters(norm.get("deals", pd.DataFrame()))
    meetings = apply_activity_filters(norm.get("meetings", pd.DataFrame()))
    tasks = apply_activity_filters(norm.get("tasks", pd.DataFrame()))
    calls = apply_activity_filters(norm.get("calls", pd.DataFrame()))
    emails = apply_activity_filters(norm.get("emails", pd.DataFrame()))
    notes = apply_activity_filters(norm.get("notes", pd.DataFrame()))
    tickets = norm.get("tickets", pd.DataFrame())

    # 7 - Metrics
    logger.info("Computing activity metrics...")
    activity = count_activities(calls, meetings, tasks, emails)
    activity_log = build_combined_activity_log(calls, meetings, tasks)

    weekly = activity.get("activity_counts_weekly", pd.DataFrame())
    rep_score = compute_activity_score(weekly.copy())
    rep_score_trend = compute_activity_score_by_period(weekly.copy())

    logger.info("Computing pipeline metrics...")
    pipe = pipeline_summary(deals)

    logger.info("Computing terminal metrics...")
    term = terminal_summary(deals)

    data = AnalyticsData(
        deals=deals, meetings=meetings, tasks=tasks, tickets=tickets, calls=calls, emails=emails, notes=notes,
        activity_counts_daily=activity.get("activity_counts_daily", pd.DataFrame()),
        activity_counts_weekly=weekly,
        activity_counts_monthly=activity.get("activity_counts_monthly", pd.DataFrame()),
        activity_log=activity_log,
        rep_activity_score=rep_score,
        rep_activity_score_trend=rep_score_trend,
        active_pipeline_value=pipe["active_pipeline_value"],
        deals_closing_this_quarter=pipe["deals_closing_this_quarter"],
        deal_count_by_stage=pipe["deal_count_by_stage"],
        avg_days_in_stage=pipe["avg_days_in_stage"],
        win_rate=pipe["win_rate"],
        closed_won_vs_lost=term["closed_won_vs_lost"],
        ncr_by_pipeline=term["ncr_by_pipeline"],
        sales_order_created=term["sales_order_created"],
        avg_sales_cycle=term["avg_sales_cycle"],
    )
    logger.info("All metrics computed.")
    return data
