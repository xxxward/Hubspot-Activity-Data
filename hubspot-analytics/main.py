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
    apply_owner_mapping, deduplicate_meetings, deduplicate_emails,
    convert_calls_to_meetings_and_dedupe,
)
from src.parsing.filters import apply_deal_filters, apply_activity_filters
from src.metrics.activity import count_activities, build_combined_activity_log
from src.metrics.pipeline import pipeline_summary
from src.metrics.terminal import terminal_summary
from src.metrics.scoring import compute_activity_score, compute_activity_score_by_period

logger = logging.getLogger(__name__)

try:
    from src.gong.gong_client import (
        fetch_gong_enrichment, fetch_gong_enrichment_range,
        map_gong_to_rep, is_gong_configured,
    )
except ImportError:
    logger.warning("Gong client not available — skipping Gong integration.")
    def fetch_gong_enrichment(*a, **kw): return pd.DataFrame()
    def fetch_gong_enrichment_range(*a, **kw): return pd.DataFrame()
    def map_gong_to_rep(name): return name
    def is_gong_configured(): return False


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
    new_pipeline: pd.DataFrame = field(default_factory=pd.DataFrame)

    # Gong call intelligence
    gong_calls: pd.DataFrame = field(default_factory=pd.DataFrame)

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
    for tab_type in ("deals", "meetings", "calls", "tasks", "tickets", "emails", "notes", "new_pipeline"):
        if tab_type in norm and not norm[tab_type].empty:
            norm[tab_type] = apply_owner_mapping(norm[tab_type], uid_map, tab_type)

    # 5 - Deduplicate meetings
    logger.info("Deduplicating meetings...")
    if not norm.get("meetings", pd.DataFrame()).empty:
        norm["meetings"] = deduplicate_meetings(norm["meetings"])

    # 5b - Convert negotiation meeting calls to meetings and cross-deduplicate
    logger.info("Converting negotiation meeting calls and cross-deduplicating...")
    if not norm.get("calls", pd.DataFrame()).empty or not norm.get("meetings", pd.DataFrame()).empty:
        norm["calls"], norm["meetings"] = convert_calls_to_meetings_and_dedupe(
            norm.get("calls", pd.DataFrame()),
            norm.get("meetings", pd.DataFrame())
        )
        
    # 5c - Deduplicate meetings AGAIN after call conversion
    logger.info("Re-deduplicating meetings after call conversion...")
    if not norm.get("meetings", pd.DataFrame()).empty:
        norm["meetings"] = deduplicate_meetings(norm["meetings"])

    # 5d - Deduplicate emails
    logger.info("Deduplicating emails...")
    if not norm.get("emails", pd.DataFrame()).empty:
        norm["emails"] = deduplicate_emails(norm["emails"])

    # 6 - Filter
    logger.info("Filtering...")
    deals = apply_deal_filters(norm.get("deals", pd.DataFrame()))
    meetings = apply_activity_filters(norm.get("meetings", pd.DataFrame()))
    tasks = apply_activity_filters(norm.get("tasks", pd.DataFrame()))
    calls = apply_activity_filters(norm.get("calls", pd.DataFrame()))
    emails = apply_activity_filters(norm.get("emails", pd.DataFrame()))
    notes = apply_activity_filters(norm.get("notes", pd.DataFrame()))
    tickets = norm.get("tickets", pd.DataFrame())
    new_pipeline = apply_activity_filters(norm.get("new_pipeline", pd.DataFrame()))

    # 6b - Gong call intelligence (optional) — fetch last 7 days for dashboard
    gong_calls = pd.DataFrame()
    if is_gong_configured():
        logger.info("Fetching Gong call data (last 7 days)...")
        try:
            from datetime import datetime, timedelta
            from zoneinfo import ZoneInfo
            _tz = ZoneInfo("America/Denver")
            _now = datetime.now(_tz)
            _from = (_now - timedelta(days=7)).replace(hour=0, minute=0, second=0, microsecond=0)
            _to = _now.replace(hour=23, minute=59, second=59, microsecond=0)
            gong_calls = fetch_gong_enrichment_range(_from, _to)
            if not gong_calls.empty:
                gong_calls["hubspot_owner_name"] = gong_calls["gong_user_name"].apply(map_gong_to_rep)
                logger.info("Gong: %d calls loaded.", len(gong_calls))
        except Exception as e:
            logger.warning("Gong fetch failed (continuing without): %s", e)
            gong_calls = pd.DataFrame()
    else:
        logger.info("Gong not configured — skipping.")

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
        deals=deals, meetings=meetings, tasks=tasks, tickets=tickets, calls=calls, emails=emails, notes=notes, new_pipeline=new_pipeline,
        gong_calls=gong_calls,
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
