"""
Main orchestrator: load -> normalize -> owner map -> dedup -> filter -> metrics.

Gong data now comes from Google Sheets (synced via Apps Script), not the Gong API.
Tasks are excluded from activity metrics.
Calls stay as calls; meetings stay as meetings (no cross-conversion).
"""

import logging
from dataclasses import dataclass, field

import pandas as pd

from src.utils.logging import setup_logging
from src.sheets.sheets_client import read_all_tabs
from src.parsing.normalize import (
    normalize_dataframe, build_uid_map_from_meetings,
    apply_owner_mapping, deduplicate_meetings, deduplicate_emails,
)
from src.parsing.filters import apply_deal_filters, apply_activity_filters, REPS_IN_SCOPE
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
    tickets: pd.DataFrame = field(default_factory=pd.DataFrame)
    calls: pd.DataFrame = field(default_factory=pd.DataFrame)
    emails: pd.DataFrame = field(default_factory=pd.DataFrame)
    notes: pd.DataFrame = field(default_factory=pd.DataFrame)
    tasks: pd.DataFrame = field(default_factory=pd.DataFrame)  # Used in Deal Health only, not in activity metrics
    new_pipeline: pd.DataFrame = field(default_factory=pd.DataFrame)

    # Gong data from Google Sheets (synced via Apps Script)
    gong_ai_summaries: pd.DataFrame = field(default_factory=pd.DataFrame)
    gong_calls: pd.DataFrame = field(default_factory=pd.DataFrame)
    gong_users: pd.DataFrame = field(default_factory=pd.DataFrame)

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


def _normalize_gong_sheet(df: pd.DataFrame, sheet_type: str) -> pd.DataFrame:
    """Light normalization for Gong sheet tabs (snake_case headers, type coercion)."""
    if df.empty:
        return df

    # Snake-case column names
    df.columns = (
        df.columns.str.strip()
        .str.lower()
        .str.replace(r"[^a-z0-9]+", "_", regex=True)
        .str.strip("_")
    )

    # Coerce numeric columns
    if sheet_type == "gong_ai_summaries":
        if "duration_sec" in df.columns:
            df["duration_sec"] = pd.to_numeric(df["duration_sec"], errors="coerce")
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"], errors="coerce")
    elif sheet_type == "gong_calls":
        if "duration_sec" in df.columns:
            df["duration_sec"] = pd.to_numeric(df["duration_sec"], errors="coerce")
        for col in ("scheduled", "started"):
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], errors="coerce")
    elif sheet_type == "gong_users":
        if "created" in df.columns:
            df["created"] = pd.to_datetime(df["created"], errors="coerce")

    return df


# Map rep emails to HubSpot rep names for Gong matching
_EMAIL_TO_REP: dict[str, str] = {
    "jlynch@calyxcontainers.com": "Jake Lynch",
    "olabombard@calyxcontainers.com": "Owen Labombard",
    "lmitton@calyxcontainers.com": "Lance Mitton",
    "dborkowski@calyxcontainers.com": "Dave Borkowski",
    "bsherman@calyxcontainers.com": "Brad Sherman",
    "xward@calyxcontainers.com": "Alex Gonzalez",
}


def _normalize_title(t: str) -> str:
    """Lowercase, strip common prefixes like [Gong], collapse whitespace."""
    import re
    t = re.sub(r"^\[gong\]\s*", "", t.strip().lower())
    return re.sub(r"\s+", " ", t).strip()


def _supplement_meetings_from_gong(
    meetings: pd.DataFrame,
    gong_ai_summaries: pd.DataFrame,
) -> pd.DataFrame:
    """
    Credit reps who were on Gong-recorded calls but aren't the HubSpot
    meeting owner.

    The Gong AI Summaries tab has the correct rep attribution — e.g.,
    a call might be 'owned' by Brittany Williams in HubSpot/Gong Calls,
    but the AI summary correctly shows Jake Lynch as the rep who was on
    the call and participated.  We use AI summaries as the source of truth.

    Deduplicates on (rep, date, normalized_title) so a rep can get credit
    for multiple calls on the same day.
    """
    if gong_ai_summaries.empty:
        return meetings

    # Find columns — AI summaries use rep_name/rep_email; prioritize those
    email_col = next((c for c in ("rep_email", "primary_rep_email") if c in gong_ai_summaries.columns), None)
    name_col = next((c for c in ("rep_name", "primary_rep") if c in gong_ai_summaries.columns), None)
    date_col = next((c for c in ("date", "started", "scheduled") if c in gong_ai_summaries.columns), None)

    if (email_col is None and name_col is None) or date_col is None:
        logger.info("Gong AI summaries missing rep or date columns — skipping supplementation.")
        return meetings

    # Resolve each Gong call's rep to a HubSpot rep name
    def _resolve_rep(row):
        if email_col and pd.notna(row.get(email_col)):
            email = str(row[email_col]).strip().lower()
            if email in _EMAIL_TO_REP:
                return _EMAIL_TO_REP[email]
        if name_col and pd.notna(row.get(name_col)):
            name = str(row[name_col]).strip()
            if name in REPS_IN_SCOPE:
                return name
        return None

    gong = gong_ai_summaries.copy()
    gong["_resolved_rep"] = gong.apply(_resolve_rep, axis=1)
    gong = gong[gong["_resolved_rep"].notna()]

    if gong.empty:
        return meetings

    gong["_gong_date"] = pd.to_datetime(gong[date_col], errors="coerce").dt.normalize()

    # Build set of (rep, date, normalized_title) already in HubSpot meetings
    existing: set[tuple[str, str, str]] = set()
    if not meetings.empty and "hubspot_owner_name" in meetings.columns and "meeting_start_time" in meetings.columns:
        mtg_dates = pd.to_datetime(meetings["meeting_start_time"], errors="coerce").dt.normalize()
        mtg_titles = meetings["meeting_name"].astype(str) if "meeting_name" in meetings.columns else pd.Series("", index=meetings.index)
        for rep, dt, title in zip(meetings["hubspot_owner_name"], mtg_dates, mtg_titles):
            if pd.notna(dt):
                existing.add((str(rep), str(dt.date()), _normalize_title(str(title))))

    # Create synthetic meeting rows for Gong calls not already credited
    new_rows = []
    for _, gc in gong.iterrows():
        rep = gc["_resolved_rep"]
        gong_date = gc["_gong_date"]
        if pd.isna(gong_date):
            continue

        title = str(gc.get("title", "Gong Call"))
        key = (rep, str(gong_date.date()), _normalize_title(title))
        if key in existing:
            continue  # This rep already has this meeting — skip

        new_rows.append({
            "meeting_start_time": gong_date,
            "hubspot_owner_name": rep,
            "meeting_name": f"[Gong] {title}",
            "company_name": gc.get("external_participants", ""),
            "meeting_outcome": "Completed",
            "meeting_source": "Gong",
            "has_gong": True,
            "_counts_as_meeting": True,
        })
        existing.add(key)

    if new_rows:
        logger.info("Gong supplementation: adding %d meetings for non-owner reps.", len(new_rows))
        meetings = pd.concat([meetings, pd.DataFrame(new_rows)], ignore_index=True)
    else:
        logger.info("Gong supplementation: no additional meetings to add.")

    return meetings


def load_all() -> AnalyticsData:
    """
    Full pipeline:
      1. Read tabs from Google Sheets (including Gong tabs)
      2. Normalize columns & types
      3. Build UID->Name map from Meetings
      4. Apply owner mapping per tab
      5. Deduplicate meetings and emails
      6. Filter by rep/pipeline/stage
      7. Compute all metrics
    """
    # 1 - Read
    logger.info("Reading Google Sheets...")
    raw = read_all_tabs()

    # 2 - Normalize HubSpot columns & types
    logger.info("Normalizing...")
    norm = {}
    hubspot_tabs = ("deals", "meetings", "calls", "tickets", "emails", "notes", "tasks", "new_pipeline")
    for k, v in raw.items():
        if k in hubspot_tabs:
            norm[k] = normalize_dataframe(v)
        else:
            norm[k] = v  # Gong tabs get separate normalization

    # Normalize Gong sheet tabs
    gong_ai_summaries = _normalize_gong_sheet(
        norm.pop("gong_ai_summaries", pd.DataFrame()), "gong_ai_summaries"
    )
    gong_calls_sheet = _normalize_gong_sheet(
        norm.pop("gong_calls", pd.DataFrame()), "gong_calls"
    )
    gong_users = _normalize_gong_sheet(
        norm.pop("gong_users", pd.DataFrame()), "gong_users"
    )

    logger.info(
        "Gong sheets: %d AI summaries, %d calls, %d users.",
        len(gong_ai_summaries), len(gong_calls_sheet), len(gong_users),
    )

    # 3 - Build UID map from meetings (the Rosetta Stone)
    logger.info("Building HubSpot UID -> Name mapping...")
    uid_map = build_uid_map_from_meetings(norm.get("meetings", pd.DataFrame()))

    # 4 - Apply owner mapping per tab type (skip tasks — not tracked)
    logger.info("Applying owner mappings...")
    for tab_type in ("deals", "meetings", "calls", "tickets", "emails", "notes", "tasks", "new_pipeline"):
        if tab_type in norm and not norm[tab_type].empty:
            norm[tab_type] = apply_owner_mapping(norm[tab_type], uid_map, tab_type)

    # 5 - Deduplicate meetings (but do NOT convert calls to meetings)
    logger.info("Deduplicating meetings...")
    if not norm.get("meetings", pd.DataFrame()).empty:
        norm["meetings"] = deduplicate_meetings(norm["meetings"])

    # 5b - Deduplicate emails
    logger.info("Deduplicating emails...")
    if not norm.get("emails", pd.DataFrame()).empty:
        norm["emails"] = deduplicate_emails(norm["emails"])

    # 6 - Filter
    logger.info("Filtering...")
    deals = apply_deal_filters(norm.get("deals", pd.DataFrame()))
    meetings = apply_activity_filters(norm.get("meetings", pd.DataFrame()))
    # Only completed meetings count as activity (exclude Scheduled, Canceled, No Show, etc.)
    if not meetings.empty and "meeting_outcome" in meetings.columns:
        meetings = meetings[meetings["meeting_outcome"].str.strip().str.lower() == "completed"]

    # 6b - Supplement meetings from Gong AI Summaries for reps who
    # participated but aren't the HubSpot owner.  AI summaries have the
    # correct rep attribution (e.g., Brittany owns the meeting in HubSpot
    # but Jake was the actual sales rep on the call).
    meetings = _supplement_meetings_from_gong(meetings, gong_ai_summaries)

    calls = apply_activity_filters(norm.get("calls", pd.DataFrame()))

    # 6c - Reclassify "Conference" calls as meetings (these are multi-party
    # meetings that HubSpot logged as calls)
    if not calls.empty and "call_direction" in calls.columns:
        conf_mask = calls["call_direction"].str.strip().str.lower() == "conference"
        conf_calls = calls[conf_mask].copy()
        if not conf_calls.empty:
            logger.info("Reclassifying %d conference calls as meetings.", len(conf_calls))
            # Map call columns to meeting columns
            conf_calls["meeting_name"] = conf_calls.get("call_title", conf_calls.get("activity_type", "Conference Call"))
            conf_calls["meeting_start_time"] = conf_calls.get("activity_date", pd.NaT)
            conf_calls["meeting_outcome"] = "Completed"
            conf_calls["meeting_source"] = "Conference Call"
            conf_calls["has_gong"] = False
            conf_calls["_counts_as_meeting"] = True
            meetings = pd.concat([meetings, conf_calls], ignore_index=True)
            calls = calls[~conf_mask]

    emails = apply_activity_filters(norm.get("emails", pd.DataFrame()))
    notes = apply_activity_filters(norm.get("notes", pd.DataFrame()))
    tickets = norm.get("tickets", pd.DataFrame())
    tasks = apply_activity_filters(norm.get("tasks", pd.DataFrame()))  # For Deal Health only
    new_pipeline = apply_activity_filters(norm.get("new_pipeline", pd.DataFrame()))

    # 7 - Metrics (no tasks)
    logger.info("Computing activity metrics...")
    activity = count_activities(calls, meetings, emails=emails)
    activity_log = build_combined_activity_log(calls, meetings, emails=emails)

    weekly = activity.get("activity_counts_weekly", pd.DataFrame())
    rep_score = compute_activity_score(weekly.copy())
    rep_score_trend = compute_activity_score_by_period(weekly.copy())

    logger.info("Computing pipeline metrics...")
    pipe = pipeline_summary(deals)

    logger.info("Computing terminal metrics...")
    term = terminal_summary(deals)

    data = AnalyticsData(
        deals=deals,
        meetings=meetings,
        tickets=tickets,
        calls=calls,
        emails=emails,
        notes=notes,
        tasks=tasks,
        new_pipeline=new_pipeline,
        gong_ai_summaries=gong_ai_summaries,
        gong_calls=gong_calls_sheet,
        gong_users=gong_users,
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
