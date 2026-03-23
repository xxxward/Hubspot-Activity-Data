"""
Main orchestrator: load -> normalize -> owner map -> dedup -> filter -> metrics.

Gong is the primary source of truth for meetings.  Every Gong Conference call
becomes a meeting row.  HubSpot Completed meetings are added only when they
don't already match a Gong call (i.e., meetings Gong wasn't recording).

Gong data comes from Google Sheets (synced via Apps Script), not the Gong API.
Tasks are excluded from activity metrics.

Both meetings AND calls are sourced from Gong primarily:
  - Meetings = Gong "Web conference" / "Conference" direction calls
  - Calls = Gong telephony calls (outbound, inbound, etc.)
HubSpot Completed meetings are added as fallback only when Gong didn't record them.
HubSpot calls are used as fallback when Gong produces zero call rows.

Gong direction values: "Web conference", "Telephony: Outbound", "Telephony: Inbound", "Conference".
"""

import glob
import logging
import os
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
        for col in ("scheduled", "started", "date"):
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], errors="coerce")
    elif sheet_type == "gong_users":
        if "created" in df.columns:
            df["created"] = pd.to_datetime(df["created"], errors="coerce")

    return df


def _read_gong_export_csvs() -> pd.DataFrame:
    """Read Gong export CSV files (Calls) from the repo root directory.

    The Gong Calls Google Sheet only contains conference/web calls.
    Telephony calls (outbound dialer) come from Gong CSV exports that
    the user adds to the repo root.  File pattern:
        *Calls*.csv
    """
    # Look in repo root (one level up from hubspot-analytics/)
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    # Also check working directory in case app runs from repo root
    search_dirs = [repo_root, os.getcwd()]
    seen_paths: set[str] = set()
    frames: list[pd.DataFrame] = []

    for search_dir in search_dirs:
        for csv_path in glob.glob(os.path.join(search_dir, "*Calls*.csv")):
            real = os.path.realpath(csv_path)
            if real in seen_paths:
                continue
            seen_paths.add(real)
            try:
                df = pd.read_csv(csv_path)
                logger.info("Read Gong CSV export: %s (%d rows)", os.path.basename(csv_path), len(df))
                frames.append(df)
            except Exception as exc:
                logger.warning("Failed to read Gong CSV %s: %s", csv_path, exc)

    if not frames:
        return pd.DataFrame()

    combined = pd.concat(frames, ignore_index=True)
    # Normalize columns same as Gong sheet tabs
    combined = _normalize_gong_sheet(combined, "gong_calls")
    logger.info("Gong CSV exports: %d total rows, columns: %s", len(combined), list(combined.columns))
    return combined


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


_RESOLVE_REPS_MISS_LOGGED = set()  # Track already-logged misses to avoid spam


def _resolve_reps(row, email_col: str | None, name_col: str | None, attendees_col: str | None) -> list[str]:
    """Resolve in-scope reps from a Gong row using email, name, and attendees columns."""
    reps = []
    seen: set[str] = set()
    if email_col and pd.notna(row.get(email_col)):
        email = str(row[email_col]).strip().lower()
        if email in _EMAIL_TO_REP:
            name = _EMAIL_TO_REP[email]
            reps.append(name)
            seen.add(name)
        elif email and email not in _RESOLVE_REPS_MISS_LOGGED:
            _RESOLVE_REPS_MISS_LOGGED.add(email)
            logger.debug("  _resolve_reps: email %r not in _EMAIL_TO_REP", email)
    if not reps and name_col and pd.notna(row.get(name_col)):
        name = str(row[name_col]).strip()
        if name in REPS_IN_SCOPE:
            reps.append(name)
            seen.add(name)
        elif name and name not in _RESOLVE_REPS_MISS_LOGGED:
            _RESOLVE_REPS_MISS_LOGGED.add(name)
            logger.debug("  _resolve_reps: name %r not in REPS_IN_SCOPE", name)
    if attendees_col:
        for extra in _resolve_attendees(row.get(attendees_col)):
            if extra not in seen:
                reps.append(extra)
                seen.add(extra)
    return reps


def _filter_conference_calls(
    gong_ai_summaries: pd.DataFrame,
    gong_calls: pd.DataFrame | None,
) -> pd.DataFrame:
    """Filter Gong AI Summaries to only Conference-direction calls."""
    if gong_calls is None or gong_calls.empty:
        logger.warning("No Gong Calls sheet — cannot filter by direction.")
        return pd.DataFrame()
    if "call_id" not in gong_ai_summaries.columns or "call_id" not in gong_calls.columns:
        logger.warning("Missing call_id column — cannot join AI summaries with Calls.")
        return pd.DataFrame()

    direction_col = next((c for c in ("direction",) if c in gong_calls.columns), None)
    if not direction_col:
        logger.warning("No direction column in Gong Calls — cannot filter.")
        return pd.DataFrame()

    call_dirs = gong_calls[["call_id", direction_col]].drop_duplicates("call_id")
    call_dirs["_dir"] = call_dirs[direction_col].astype(str).str.strip().str.lower()

    direction_counts = call_dirs["_dir"].value_counts()
    logger.info("Gong Calls direction distribution: %s", direction_counts.to_dict())

    conference_ids = set(call_dirs.loc[call_dirs["_dir"].str.contains("conference", na=False), "call_id"])
    logger.info("Conference call_ids: %d", len(conference_ids))

    # Diagnostic: show sample call_ids from each source to detect mismatches
    sample_summ = list(gong_ai_summaries["call_id"].head(3))
    sample_calls = list(call_dirs["call_id"].head(3))
    sample_conf = list(conference_ids)[:3] if conference_ids else []
    logger.info(
        "call_id samples — AI Summaries: %s (dtype=%s), Calls: %s (dtype=%s), Conference: %s",
        sample_summ, gong_ai_summaries["call_id"].dtype,
        sample_calls, call_dirs["call_id"].dtype,
        sample_conf,
    )

    # Check for overlap
    summaries_set = set(gong_ai_summaries["call_id"])
    overlap = summaries_set & conference_ids
    logger.info(
        "call_id overlap: %d summaries, %d conference, %d matched.",
        len(summaries_set), len(conference_ids), len(overlap),
    )

    before = len(gong_ai_summaries)
    result = gong_ai_summaries[gong_ai_summaries["call_id"].isin(conference_ids)].copy()
    logger.info("Gong direction filter: %d -> %d entries (Conference only).", before, len(result))
    return result


def _build_meetings_gong_primary(
    hubspot_meetings: pd.DataFrame,
    gong_ai_summaries: pd.DataFrame,
    gong_calls: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """
    Build the canonical meetings table with **Gong as the primary source of
    truth** and HubSpot as the fallback.

    Flow:
      1. Start with Gong Conference calls (from AI Summaries + Calls sheets).
         Every Conference call where we can identify an in-scope rep becomes
         a meeting row.
      2. Then check HubSpot Completed meetings.  Any HubSpot meeting that
         does NOT fuzzy-match a Gong meeting (same rep + date + title) is
         added — these are meetings Gong didn't record.

    This matches how the business actually thinks about it: if it was
    recorded in Gong, it happened.  HubSpot catches the rest.
    """

    # ── Step 0: Normalize call_id to string to avoid type mismatches ──
    if not gong_ai_summaries.empty and "call_id" in gong_ai_summaries.columns:
        gong_ai_summaries = gong_ai_summaries.copy()
        gong_ai_summaries["call_id"] = gong_ai_summaries["call_id"].astype(str).str.strip()
    if gong_calls is not None and not gong_calls.empty and "call_id" in gong_calls.columns:
        gong_calls = gong_calls.copy()
        gong_calls["call_id"] = gong_calls["call_id"].astype(str).str.strip()

    # ── Step 1: Build meetings from Gong Conference calls (PRIMARY) ──
    gong_rows: list[dict] = []
    # Track (rep, date) -> [titles] for dedup against HubSpot later
    gong_titles: dict[tuple[str, str], list[str]] = {}

    if not gong_ai_summaries.empty:
        gong_conf = _filter_conference_calls(gong_ai_summaries, gong_calls)

        if not gong_conf.empty:
            email_col = next((c for c in ("rep_email", "primary_rep_email") if c in gong_conf.columns), None)
            name_col = next((c for c in ("rep_name", "primary_rep") if c in gong_conf.columns), None)
            date_col = next((c for c in ("date", "started", "scheduled") if c in gong_conf.columns), None)
            attendees_col = next((c for c in ("all_attendees",) if c in gong_conf.columns), None)

            if date_col and (email_col or name_col):
                gong = gong_conf.copy()
                gong_dates = pd.to_datetime(gong[date_col], errors="coerce")
                if gong_dates.dt.tz is not None:
                    gong_dates = gong_dates.dt.tz_localize(None)
                gong["_gong_date"] = gong_dates.dt.normalize()

                for _, gc in gong.iterrows():
                    gong_date = gc["_gong_date"]
                    if pd.isna(gong_date):
                        continue

                    reps = _resolve_reps(gc, email_col, name_col, attendees_col)
                    if not reps:
                        logger.debug(
                            "  Gong primary: NO REP for call_id=%s title=%r",
                            gc.get("call_id", "?"), gc.get("title", "?"),
                        )
                        continue

                    title = str(gc.get("title", "Gong Call"))

                    for rep in reps:
                        date_key = (rep, str(gong_date.date()))

                        # Dedup within Gong itself (same rep+date+title)
                        already = False
                        for et in gong_titles.get(date_key, []):
                            if _titles_match(title, et):
                                already = True
                                break
                        if already:
                            continue

                        gong_rows.append({
                            "meeting_start_time": gong_date,
                            "hubspot_owner_name": rep,
                            "meeting_name": f"[Gong] {title}",
                            "company_name": gc.get("external_participants", ""),
                            "meeting_outcome": "Completed",
                            "meeting_source": "Gong",
                            "has_gong": True,
                            "_counts_as_meeting": True,
                        })
                        gong_titles.setdefault(date_key, []).append(title)

    logger.info("Gong primary: built %d meeting rows from Conference calls.", len(gong_rows))

    # ── Step 1b: Gong Calls sheet fallback for calls missing from AI Summaries ──
    if gong_calls is not None and not gong_calls.empty:
        gc_title_col = next((c for c in ("title", "call_title", "name") if c in gong_calls.columns), None)
        gc_email_col = next((c for c in ("primary_rep_email", "owner_email", "rep_email", "host_email") if c in gong_calls.columns), None)
        gc_name_col = next((c for c in ("primary_rep", "owner_name", "host", "rep_name") if c in gong_calls.columns), None)
        gc_date_col = next((c for c in ("started", "scheduled", "date") if c in gong_calls.columns), None)
        gc_company_col = next((c for c in ("external_participants", "company", "account") if c in gong_calls.columns), None)
        direction_col = next((c for c in ("direction",) if c in gong_calls.columns), None)

        if gc_title_col and gc_date_col and direction_col and (gc_email_col or gc_name_col):
            conf_mask = gong_calls[direction_col].astype(str).str.strip().str.lower().str.contains("conference", na=False)
            gc_conf = gong_calls[conf_mask].copy()

            # Exclude call_ids already processed from AI summaries
            processed_ids = set(gong_ai_summaries["call_id"]) if not gong_ai_summaries.empty and "call_id" in gong_ai_summaries.columns else set()
            if "call_id" in gc_conf.columns and processed_ids:
                gc_conf = gc_conf[~gc_conf["call_id"].isin(processed_ids)]

            fallback_count = 0
            for _, gc_row in gc_conf.iterrows():
                gc_date = pd.to_datetime(gc_row.get(gc_date_col), errors="coerce")
                if pd.isna(gc_date):
                    continue
                if gc_date.tzinfo is not None:
                    gc_date = gc_date.tz_localize(None)
                gc_date = gc_date.normalize()

                fb_reps = _resolve_reps(gc_row, gc_email_col, gc_name_col, None)
                if not fb_reps:
                    continue

                fb_title = str(gc_row.get(gc_title_col, "Gong Call"))
                fb_company = str(gc_row.get(gc_company_col, "")) if gc_company_col and pd.notna(gc_row.get(gc_company_col)) else ""

                for fb_rep in fb_reps:
                    fb_key = (fb_rep, str(gc_date.date()))
                    fb_already = False
                    for et in gong_titles.get(fb_key, []):
                        if _titles_match(fb_title, et):
                            fb_already = True
                            break
                    if fb_already:
                        continue

                    gong_rows.append({
                        "meeting_start_time": gc_date,
                        "hubspot_owner_name": fb_rep,
                        "meeting_name": f"[Gong] {fb_title}",
                        "company_name": fb_company,
                        "meeting_outcome": "Completed",
                        "meeting_source": "Gong",
                        "has_gong": True,
                        "_counts_as_meeting": True,
                    })
                    gong_titles.setdefault(fb_key, []).append(fb_title)
                    fallback_count += 1

            if fallback_count:
                logger.info("Gong Calls fallback: added %d additional meetings.", fallback_count)

    # ── Step 2: Supplement with HubSpot meetings NOT in Gong (SECONDARY) ──
    hubspot_only: list[dict] = []
    if not hubspot_meetings.empty and "hubspot_owner_name" in hubspot_meetings.columns:
        mtg_dates = pd.to_datetime(hubspot_meetings["meeting_start_time"], errors="coerce") if "meeting_start_time" in hubspot_meetings.columns else pd.Series(dtype="datetime64[ns]")
        if mtg_dates.dt.tz is not None:
            mtg_dates = mtg_dates.dt.tz_localize(None)

        for idx, row in hubspot_meetings.iterrows():
            dt = mtg_dates.get(idx)
            if pd.isna(dt):
                continue
            dt_norm = dt.normalize()
            rep = str(row.get("hubspot_owner_name", ""))
            hs_title = str(row.get("meeting_name", ""))
            date_key = (rep, str(dt_norm.date()))

            # Check if this HubSpot meeting already matches a Gong meeting
            matched = False
            for gt in gong_titles.get(date_key, []):
                if _titles_match(hs_title, gt):
                    matched = True
                    break
            if matched:
                continue

            # HubSpot meeting not in Gong — keep it
            hubspot_only.append(idx)

        logger.info(
            "HubSpot secondary: %d of %d meetings not matched in Gong (keeping as HubSpot-only).",
            len(hubspot_only), len(hubspot_meetings),
        )

    # ── Combine: Gong meetings + unmatched HubSpot meetings ──
    parts = []
    if gong_rows:
        parts.append(pd.DataFrame(gong_rows))
    if hubspot_only and not hubspot_meetings.empty:
        hs_keep = hubspot_meetings.loc[hubspot_only].copy()
        hs_keep["has_gong"] = False
        parts.append(hs_keep)

    if parts:
        result = pd.concat(parts, ignore_index=True)
    elif not hubspot_meetings.empty:
        logger.warning(
            "Gong produced 0 meeting rows and no HubSpot-only matches found. "
            "Falling back to ALL %d HubSpot meetings.",
            len(hubspot_meetings),
        )
        result = hubspot_meetings.copy()
        result["has_gong"] = False
    else:
        result = pd.DataFrame()

    logger.info(
        "Meeting build complete: %d Gong + %d HubSpot-only = %d total.",
        len(gong_rows), len(hubspot_only), len(result),
    )
    return result


def _build_calls_from_gong(
    gong_ai_summaries: pd.DataFrame,
    gong_calls: pd.DataFrame | None = None,
    hubspot_calls: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """
    Build the calls table from Gong data, with HubSpot as fallback.

    Non-conference Gong calls (outbound, inbound, etc.) become call rows.
    Uses AI Summaries as the primary source (enriched data), with the
    Gong Calls sheet as fallback for calls missing from AI Summaries.

    If Gong produces zero call rows, falls back to HubSpot calls entirely.

    Deduplication is by call_id only — each unique Gong call is a distinct
    activity.  No fuzzy title matching (unlike meetings), because a rep can
    legitimately make multiple calls to the same company in one day.
    """
    call_rows: list[dict] = []
    seen_call_ids: set[str] = set()  # Dedup by call_id, not title

    # ── Step 0: Normalize call_id to string ──
    if not gong_ai_summaries.empty and "call_id" in gong_ai_summaries.columns:
        gong_ai_summaries = gong_ai_summaries.copy()
        gong_ai_summaries["call_id"] = gong_ai_summaries["call_id"].astype(str).str.strip()
    if gong_calls is not None and not gong_calls.empty and "call_id" in gong_calls.columns:
        gong_calls = gong_calls.copy()
        gong_calls["call_id"] = gong_calls["call_id"].astype(str).str.strip()

    # ── Step 1: Non-conference AI Summaries (PRIMARY — enriched data) ──
    if not gong_ai_summaries.empty and gong_calls is not None and not gong_calls.empty:
        if "call_id" in gong_ai_summaries.columns and "call_id" in gong_calls.columns:
            direction_col = next((c for c in ("direction",) if c in gong_calls.columns), None)
            if direction_col:
                call_dirs = gong_calls[["call_id", direction_col]].drop_duplicates("call_id")
                call_dirs["_dir"] = call_dirs[direction_col].astype(str).str.strip().str.lower()
                non_conf_ids = set(call_dirs.loc[~call_dirs["_dir"].str.contains("conference", na=False), "call_id"])

                gong_non_conf = gong_ai_summaries[gong_ai_summaries["call_id"].isin(non_conf_ids)].copy()
                logger.info("Gong calls from AI Summaries: %d non-conference entries.", len(gong_non_conf))

                if not gong_non_conf.empty:
                    email_col = next((c for c in ("rep_email", "primary_rep_email") if c in gong_non_conf.columns), None)
                    name_col = next((c for c in ("rep_name", "primary_rep") if c in gong_non_conf.columns), None)
                    date_col = next((c for c in ("date", "started", "scheduled") if c in gong_non_conf.columns), None)
                    attendees_col = next((c for c in ("all_attendees",) if c in gong_non_conf.columns), None)

                    if date_col and (email_col or name_col):
                        gong_dates = pd.to_datetime(gong_non_conf[date_col], errors="coerce")
                        if gong_dates.dt.tz is not None:
                            gong_dates = gong_dates.dt.tz_localize(None)
                        gong_non_conf["_gong_date"] = gong_dates.dt.normalize()

                        for _, row in gong_non_conf.iterrows():
                            gong_date = row["_gong_date"]
                            if pd.isna(gong_date):
                                continue
                            cid = str(row.get("call_id", ""))
                            reps = _resolve_reps(row, email_col, name_col, attendees_col)
                            if not reps:
                                continue
                            title = str(row.get("title", "Gong Call"))
                            for rep in reps:
                                dedup_key = f"{cid}:{rep}"
                                if dedup_key in seen_call_ids:
                                    continue
                                seen_call_ids.add(dedup_key)
                                call_rows.append({
                                    "activity_date": gong_date,
                                    "hubspot_owner_name": rep,
                                    "call_title": f"[Gong] {title}",
                                    "company_name": row.get("external_participants", ""),
                                    "call_source": "Gong",
                                    "call_id": cid,
                                })

    logger.info("Gong calls (AI Summaries): %d call rows.", len(call_rows))

    # ── Step 2: Gong Calls sheet fallback for calls missing from AI Summaries ──
    if gong_calls is not None and not gong_calls.empty:
        gc_title_col = next((c for c in ("title", "call_title", "name") if c in gong_calls.columns), None)
        gc_email_col = next((c for c in ("primary_rep_email", "owner_email", "rep_email", "host_email") if c in gong_calls.columns), None)
        gc_name_col = next((c for c in ("primary_rep", "owner_name", "host", "rep_name") if c in gong_calls.columns), None)
        gc_date_col = next((c for c in ("started", "scheduled", "date") if c in gong_calls.columns), None)
        gc_company_col = next((c for c in ("external_participants", "company", "account") if c in gong_calls.columns), None)
        direction_col = next((c for c in ("direction",) if c in gong_calls.columns), None)

        if gc_title_col and gc_date_col and direction_col and (gc_email_col or gc_name_col):
            non_conf_mask = ~gong_calls[direction_col].astype(str).str.strip().str.lower().str.contains("conference", na=False)
            gc_non_conf = gong_calls[non_conf_mask].copy()

            # Exclude call_ids already processed from AI summaries
            processed_ids = set(gong_ai_summaries["call_id"]) if not gong_ai_summaries.empty and "call_id" in gong_ai_summaries.columns else set()
            if "call_id" in gc_non_conf.columns and processed_ids:
                gc_non_conf = gc_non_conf[~gc_non_conf["call_id"].isin(processed_ids)]

            fallback_count = 0
            for _, gc_row in gc_non_conf.iterrows():
                gc_date = pd.to_datetime(gc_row.get(gc_date_col), errors="coerce")
                if pd.isna(gc_date):
                    continue
                if gc_date.tzinfo is not None:
                    gc_date = gc_date.tz_localize(None)
                gc_date = gc_date.normalize()

                cid = str(gc_row.get("call_id", ""))
                fb_reps = _resolve_reps(gc_row, gc_email_col, gc_name_col, None)
                if not fb_reps:
                    continue

                fb_title = str(gc_row.get(gc_title_col, "Gong Call"))
                fb_company = str(gc_row.get(gc_company_col, "")) if gc_company_col and pd.notna(gc_row.get(gc_company_col)) else ""

                for fb_rep in fb_reps:
                    dedup_key = f"{cid}:{fb_rep}"
                    if dedup_key in seen_call_ids:
                        continue
                    seen_call_ids.add(dedup_key)
                    call_rows.append({
                        "activity_date": gc_date,
                        "hubspot_owner_name": fb_rep,
                        "call_title": f"[Gong] {fb_title}",
                        "company_name": fb_company,
                        "call_source": "Gong",
                        "call_id": cid,
                    })
                    fallback_count += 1

            if fallback_count:
                logger.info("Gong Calls fallback: added %d additional calls.", fallback_count)

    if call_rows:
        result = pd.DataFrame(call_rows)
        logger.info("Call build complete: %d total Gong calls.", len(result))
        return result

    # ── Fallback: If Gong produced zero calls, use HubSpot calls ──
    logger.warning(
        "Gong produced 0 call rows — falling back to HubSpot calls. "
        "Check Gong sheet column names and rep email/name mappings."
    )
    if hubspot_calls is not None and not hubspot_calls.empty:
        logger.info("HubSpot calls fallback: using %d HubSpot call rows.", len(hubspot_calls))
        return hubspot_calls
    logger.warning("HubSpot calls also empty — returning empty calls DataFrame.")
    return pd.DataFrame(columns=["activity_date", "hubspot_owner_name", "call_title", "company_name", "call_source"])


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
    hubspot_tabs = ("deals", "meetings", "calls", "tickets", "emails", "notes", "tasks", "new_pipeline", "pre_order_support")
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

    # Supplement Gong Calls sheet with CSV exports (telephony calls)
    gong_csv_calls = _read_gong_export_csvs()
    if not gong_csv_calls.empty:
        if gong_calls_sheet.empty:
            gong_calls_sheet = gong_csv_calls
        else:
            # Merge, dedup by call_id
            combined = pd.concat([gong_calls_sheet, gong_csv_calls], ignore_index=True)
            if "call_id" in combined.columns:
                combined = combined.drop_duplicates(subset=["call_id"], keep="first")
            gong_calls_sheet = combined
        logger.info("After CSV merge: %d total Gong Calls rows.", len(gong_calls_sheet))

    logger.info(
        "Gong sheets: %d AI summaries, %d calls, %d users.",
        len(gong_ai_summaries), len(gong_calls_sheet), len(gong_users),
    )
    if not gong_ai_summaries.empty:
        logger.info("Gong AI Summaries columns: %s", list(gong_ai_summaries.columns))
    if not gong_calls_sheet.empty:
        logger.info("Gong Calls columns: %s", list(gong_calls_sheet.columns))

    # 3 - Build UID map from meetings (the Rosetta Stone)
    logger.info("Building HubSpot UID -> Name mapping...")
    uid_map = build_uid_map_from_meetings(norm.get("meetings", pd.DataFrame()))

    # 4 - Apply owner mapping per tab type (skip tasks — not tracked)
    logger.info("Applying owner mappings...")
    for tab_type in ("deals", "meetings", "calls", "tickets", "emails", "notes", "tasks", "new_pipeline", "pre_order_support"):
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

    # 6b - Build meetings: Gong is the primary source of truth.
    # Every Gong Conference call = a meeting.  HubSpot Completed meetings
    # that don't match a Gong call are added as fallback (meetings where
    # Gong wasn't recording).
    hubspot_meetings = apply_activity_filters(norm.get("meetings", pd.DataFrame()))
    if not hubspot_meetings.empty and "meeting_outcome" in hubspot_meetings.columns:
        hubspot_meetings = hubspot_meetings[hubspot_meetings["meeting_outcome"].str.strip().str.lower() == "completed"]
    meetings = _build_meetings_gong_primary(hubspot_meetings, gong_ai_summaries, gong_calls_sheet)

    # 6c - Build calls: Gong is the primary source for calls, HubSpot fallback.
    # Non-conference Gong calls (outbound, inbound, etc.) = calls.
    # Conference Gong calls = meetings (handled above).
    # If Gong produces zero calls, falls back to HubSpot calls.
    hubspot_calls = apply_activity_filters(norm.get("calls", pd.DataFrame()))
    calls = _build_calls_from_gong(gong_ai_summaries, gong_calls_sheet, hubspot_calls)

    emails = apply_activity_filters(norm.get("emails", pd.DataFrame()))
    notes = apply_activity_filters(norm.get("notes", pd.DataFrame()))
    # Merge Pre Order Support (new estimate tickets) into the tickets dataset.
    # Old estimates: Tickets tab (pipeline != "Sample Kit").
    # New estimates: Pre Order Support tab (all rows are estimates).
    tickets = norm.get("tickets", pd.DataFrame())
    pre_order_df = apply_activity_filters(norm.get("pre_order_support", pd.DataFrame()))
    if not pre_order_df.empty:
        pre_order_df = pre_order_df.copy()
        pre_order_df["_source"] = "pre_order_support"
        logger.info("Merging %d Pre Order Support rows into tickets.", len(pre_order_df))
        for col in ("created_date", "hubspot_owner_name", "pipeline"):
            if col not in tickets.columns and not tickets.empty:
                tickets[col] = pd.NaT if col == "created_date" else ""
            if col not in pre_order_df.columns:
                pre_order_df[col] = pd.NaT if col == "created_date" else ""
        tickets = pd.concat([tickets, pre_order_df], ignore_index=True)

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
