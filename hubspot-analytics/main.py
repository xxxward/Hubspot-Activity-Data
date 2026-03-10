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
    """Strip common prefixes and noise from meeting titles for dedup matching."""
    import re
    t = t.strip().lower()
    # Strip [Gong] prefix
    t = re.sub(r"^\[gong\]\s*", "", t)
    # Strip "Google Meet:" prefix
    t = re.sub(r"^google meet:\s*", "", t)
    # Strip "Call with <Company> - " prefix (e.g., "Call with Buckeye Relief - Ben Begley")
    t = re.sub(r"^call with\s+.+?\s*-\s*", "", t)
    # Strip "Calyx" and common filler words for matching
    t = re.sub(r"\bcalyx\b", "", t)
    # Collapse whitespace, strip punctuation except <>
    t = re.sub(r"[<>]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _title_tokens(t: str) -> set[str]:
    """Extract meaningful tokens from a normalized title for fuzzy matching."""
    norm = _normalize_title(t)
    # Extract tokens >= 2 chars, skip noise words
    noise = {"the", "and", "for", "with", "from", "this", "that", "our",
             "connect", "meeting", "call", "weekly", "check", "in"}
    return {tok for tok in norm.split() if len(tok) >= 2 and tok not in noise}


def _titles_match(title_a: str, title_b: str) -> bool:
    """Check if two meeting titles refer to the same meeting using token overlap."""
    tokens_a = _title_tokens(title_a)
    tokens_b = _title_tokens(title_b)
    if not tokens_a or not tokens_b:
        return False
    overlap = tokens_a & tokens_b
    # Match if any shared meaningful tokens (person names, company names)
    smaller = min(len(tokens_a), len(tokens_b))
    return len(overlap) >= 1 and len(overlap) / smaller >= 0.5


def _resolve_attendees(attendees_value) -> list[str]:
    """Parse the all_attendees column into a list of in-scope rep names.

    The column contains comma-separated names or emails, e.g.:
      "Jake Lynch, Owen Labombard"
      "jlynch@calyxcontainers.com, olabombard@calyxcontainers.com"
    """
    if pd.isna(attendees_value):
        return []
    raw = str(attendees_value).strip()
    if not raw:
        return []

    reps = []
    seen = set()
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        # Try as email first
        email_lower = part.lower()
        if email_lower in _EMAIL_TO_REP:
            name = _EMAIL_TO_REP[email_lower]
            if name not in seen:
                reps.append(name)
                seen.add(name)
            continue
        # Try as name
        if part in REPS_IN_SCOPE:
            if part not in seen:
                reps.append(part)
                seen.add(part)
            continue
        # Try partial / case-insensitive name match
        part_lower = part.lower()
        for rep_name in REPS_IN_SCOPE:
            if rep_name.lower() == part_lower and rep_name not in seen:
                reps.append(rep_name)
                seen.add(rep_name)
                break
    return reps


def _supplement_meetings_from_gong(
    meetings: pd.DataFrame,
    gong_ai_summaries: pd.DataFrame,
    gong_calls: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """
    Credit reps who attended Gong-recorded meetings but aren't the HubSpot
    meeting owner.

    Uses the ``all_attendees`` column (added to both Gong AI Summaries and
    Gong Calls tabs) to identify every in-scope rep on a call.  Falls back
    to the primary rep columns (rep_email / rep_name) when all_attendees is
    not available.

    Only adds entries where the Gong Calls tab shows direction="Conference"
    (actual meetings).  Inbound/Outbound calls are phone calls, not meetings.

    Deduplicates using fuzzy title matching — the same meeting can appear as:
      "Google Meet: Ben <> Jake" (HubSpot)
      "Ben <> Jake" (Gong AI Summary)
      "Call with Buckeye Relief - Ben Begley" (Gong AI Summary)
    """
    if gong_ai_summaries.empty:
        return meetings

    # Filter AI summaries to only Conference-type calls (actual meetings)
    if gong_calls is not None and not gong_calls.empty and "call_id" in gong_ai_summaries.columns and "call_id" in gong_calls.columns:
        direction_col = next((c for c in ("direction",) if c in gong_calls.columns), None)
        if direction_col:
            # Build call_id -> direction lookup from gong_calls
            call_directions = gong_calls[["call_id", direction_col]].drop_duplicates("call_id")
            call_directions["_direction_lower"] = call_directions[direction_col].astype(str).str.strip().str.lower()
            conference_ids = set(call_directions.loc[call_directions["_direction_lower"] == "conference", "call_id"])
            before = len(gong_ai_summaries)
            gong_ai_summaries = gong_ai_summaries[gong_ai_summaries["call_id"].isin(conference_ids)]
            logger.info("Gong direction filter: %d -> %d entries (Conference only).", before, len(gong_ai_summaries))
            if gong_ai_summaries.empty:
                return meetings
    else:
        logger.warning("Cannot filter Gong by direction — missing call_id or gong_calls. Skipping supplementation.")
        return meetings

    # Detect the all_attendees column (snake_case normalized)
    attendees_col = next((c for c in ("all_attendees",) if c in gong_ai_summaries.columns), None)

    # Fallback columns for primary rep (used when all_attendees is absent)
    email_col = next((c for c in ("rep_email", "primary_rep_email") if c in gong_ai_summaries.columns), None)
    name_col = next((c for c in ("rep_name", "primary_rep") if c in gong_ai_summaries.columns), None)
    date_col = next((c for c in ("date", "started", "scheduled") if c in gong_ai_summaries.columns), None)

    if attendees_col is None and email_col is None and name_col is None:
        logger.info("Gong AI summaries missing attendee and rep columns — skipping supplementation.")
        return meetings
    if date_col is None:
        logger.info("Gong AI summaries missing date column — skipping supplementation.")
        return meetings

    if attendees_col:
        logger.info("Using all_attendees column for Gong meeting attribution.")

    gong = gong_ai_summaries.copy()

    gong_dates = pd.to_datetime(gong[date_col], errors="coerce")
    if gong_dates.dt.tz is not None:
        gong_dates = gong_dates.dt.tz_localize(None)
    gong["_gong_date"] = gong_dates.dt.normalize()

    # Build index of existing meeting titles per (rep, date) for fuzzy matching
    existing_titles: dict[tuple[str, str], list[str]] = {}
    if not meetings.empty and "hubspot_owner_name" in meetings.columns and "meeting_start_time" in meetings.columns:
        mtg_dates = pd.to_datetime(meetings["meeting_start_time"], errors="coerce")
        if mtg_dates.dt.tz is not None:
            mtg_dates = mtg_dates.dt.tz_localize(None)
        mtg_dates = mtg_dates.dt.normalize()
        mtg_titles = meetings["meeting_name"].astype(str) if "meeting_name" in meetings.columns else pd.Series("", index=meetings.index)
        for rep, dt, title in zip(meetings["hubspot_owner_name"], mtg_dates, mtg_titles):
            if pd.notna(dt):
                key = (str(rep), str(dt.date()))
                existing_titles.setdefault(key, []).append(str(title))

    # Create synthetic meeting rows for Gong calls not already credited
    new_rows = []
    for _, gc in gong.iterrows():
        gong_date = gc["_gong_date"]
        if pd.isna(gong_date):
            continue

        # Resolve all attending reps from the all_attendees column
        if attendees_col:
            reps = _resolve_attendees(gc.get(attendees_col))
        else:
            # Fallback: resolve single primary rep from email/name columns
            reps = []
            if email_col and pd.notna(gc.get(email_col)):
                email = str(gc[email_col]).strip().lower()
                if email in _EMAIL_TO_REP:
                    reps.append(_EMAIL_TO_REP[email])
            if not reps and name_col and pd.notna(gc.get(name_col)):
                name = str(gc[name_col]).strip()
                if name in REPS_IN_SCOPE:
                    reps.append(name)

        if not reps:
            continue

        title = str(gc.get("title", "Gong Call"))

        for rep in reps:
            date_key = (rep, str(gong_date.date()))

            # Check if this Gong call fuzzy-matches any existing meeting for this rep+date
            already_exists = False
            for existing_title in existing_titles.get(date_key, []):
                if _titles_match(title, existing_title):
                    already_exists = True
                    break
            if already_exists:
                continue

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
            # Add to existing so subsequent Gong entries also dedup against this one
            existing_titles.setdefault(date_key, []).append(f"[Gong] {title}")

    if new_rows:
        logger.info("Gong supplementation: adding %d meetings from attendees.", len(new_rows))
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
    meetings = _supplement_meetings_from_gong(meetings, gong_ai_summaries, gong_calls_sheet)

    calls = apply_activity_filters(norm.get("calls", pd.DataFrame()))

    # Note: Conference calls are NOT reclassified as meetings here.
    # Real meetings are captured via HubSpot meetings (Completed outcome)
    # + Gong AI Summaries (Conference direction).  Reclassifying HubSpot
    # "conference" calls inflated SDR meeting counts (e.g., Owen's multi-line dials).

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
