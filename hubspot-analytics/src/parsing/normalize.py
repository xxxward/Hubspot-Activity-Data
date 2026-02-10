"""
Column normalization: snake_case conversion, alias mapping, type coercion.

Also handles:
  - Coefficient row-2 headers (handled in sheets_client)
  - Duplicate column deduplication
  - HubSpot User ID -> Rep Name mapping (built from Meetings tab)
  - Meeting deduplication ([Gong], Google Meet:, blank-name merging)
"""

import re
import logging
from collections import defaultdict
from datetime import datetime

import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)

# -- snake_case helper ---------------------------------------------------

def to_snake_case(name: str) -> str:
    s = re.sub(r"[\s\-\.\/\(\)]+", "_", str(name).strip())
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s)
    s = re.sub(r"_+", "_", s).lower().strip("_")
    return s


# -- Column alias map ----------------------------------------------------

COLUMN_ALIASES: dict[str, str] = {
    # Deals
    "create_date": "created_date",
    "associated_company_name": "company_name",
    "hub_spot_team": "hubspot_team",
    "opp_owner": "hubspot_owner_name",
    "opp_type_no_blanks": "opp_type",
    "is_deal_closed?": "is_deal_closed",
    # Meetings
    "activity_assigned_to": "activity_assigned_to",
    "activity_created_by": "activity_created_by",
    "body_preview_truncated": "body_preview",
    # Tasks
    "created_at": "created_date",
    "completed_at": "completed_at",
    "last_modified_at": "last_modified_date",
    "notes_preview": "notes_preview",
    # Calls
    "last_modified_date": "last_modified_date",
    # Emails
    "email_id": "email_id",
    "email_from_address": "email_from_address",
    "email_to_address": "email_to_address",
    "number_of_email_opens": "email_opens",
    "number_of_email_clicks": "email_clicks",
    "number_of_email_replies": "email_replies",
    "email_open_rate": "email_open_rate",
    "email_click_rate": "email_click_rate",
    "email_reply_rate": "email_reply_rate",
    "email_cc_address": "email_cc_address",
    "first_name_activity_assigned_to": "owner_first_name",
    "last_name_activity_assigned_to": "owner_last_name",
    "created_by_user_id": "created_by_user_id",
    "hub_spot_team": "hubspot_team",
    "updated_by_user_id": "updated_by_user_id",
    # Notes
    "note_id": "note_id",
    "note_body": "note_body",
    "deal_name": "deal_name",
    # Tickets
    "first_name_ticket_owner": "ticket_owner_first_name",
}

DATE_COLUMNS = {
    "created_date", "close_date", "activity_date", "meeting_start_time",
    "meeting_end_time", "completed_at", "due_date", "last_modified_date",
    "create_date", "last_activity_date", "next_activity_date",
}

NUMERIC_COLUMNS = {
    "amount", "deal_id", "company_id", "call_duration", "ticket_id",
    "opp_age", "forecast_probability", "call_id",
}


# -- HubSpot User ID -> Rep Name mapping ---------------------------------

# Hardcoded confirmed mapping (from the Meetings Rosetta Stone)
HUBSPOT_UID_TO_NAME: dict[str, str] = {
    "56564763": "Alex Gonzalez",
    "56562506": "Brad Sherman",
    "119721604": "Dave Borkowski",
    "56564944": "Jake Lynch",
    "79617483": "Lance Mitton",
    "85412002": "Owen Labombard",
}


def _clean_uid(val) -> str:
    """Clean a HubSpot User ID value — handle float, int, string forms."""
    if pd.isna(val) or val == "" or val is None:
        return ""
    s = str(val).strip()
    # Strip .0 suffix from float representation
    if s.endswith(".0"):
        s = s[:-2]
    return s


def build_uid_map_from_meetings(meetings_df: pd.DataFrame) -> dict[str, str]:
    """
    Build User ID -> Name mapping from the Meetings tab.
    Falls back to hardcoded map if meetings data is insufficient.
    """
    from src.parsing.filters import REPS_IN_SCOPE

    uid_map = dict(HUBSPOT_UID_TO_NAME)  # start with known mapping

    if meetings_df.empty:
        return uid_map

    # Try to enrich from the actual meetings data
    first_col = "first_name" if "first_name" in meetings_df.columns else None
    last_col = "last_name" if "last_name" in meetings_df.columns else None
    uid_col = "activity_assigned_to" if "activity_assigned_to" in meetings_df.columns else None

    if first_col and last_col and uid_col:
        for _, row in meetings_df.iterrows():
            first = str(row.get(first_col, "")).strip()
            last = str(row.get(last_col, "")).strip()
            name = f"{first} {last}".strip()
            if name in REPS_IN_SCOPE:
                uid = _clean_uid(row.get(uid_col))
                if uid:
                    uid_map[uid] = name

    logger.info("UID map built with %d entries: %s", len(uid_map), uid_map)
    return uid_map


def apply_owner_mapping(df: pd.DataFrame, uid_map: dict[str, str], tab_type: str) -> pd.DataFrame:
    """
    Apply the correct owner mapping strategy per tab type.

    - meetings: First name + Last name = rep name
    - calls: Activity assigned to (UID) -> name via uid_map
    - tasks: full_name is already the rep name
    - tickets: First name + Last name = rep name
    - deals: hubspot_owner_name already mapped from Opp Owner
    """
    if df.empty:
        return df
    df = df.copy()

    if tab_type == "meetings":
        # Build rep name from first + last
        first = df.get("first_name", pd.Series("", index=df.index)).fillna("").astype(str).str.strip()
        last = df.get("last_name", pd.Series("", index=df.index)).fillna("").astype(str).str.strip()
        df["hubspot_owner_name"] = (first + " " + last).str.strip()

    elif tab_type == "calls":
        # Map UID to name
        uid_col = "activity_assigned_to" if "activity_assigned_to" in df.columns else "hubspot_owner_name"
        df["hubspot_owner_name"] = df[uid_col].apply(lambda x: uid_map.get(_clean_uid(x), ""))

    elif tab_type == "tasks":
        # full_name is the rep
        if "full_name" in df.columns:
            df["hubspot_owner_name"] = df["full_name"]

    elif tab_type == "emails":
        # Emails have first_name/last_name (Activity assigned to) and activity_assigned_to (UID)
        # Build name from first + last name columns, or map UID
        REP_LAST_NAMES = {"Sherman", "Labombard", "Lynch", "Borkowski", "Gonzalez", "Mitton"}

        logger.info("Emails columns before owner mapping: %s", list(df.columns))

        # Try owner_first_name + owner_last_name first (from "First name (Activity assigned to)" etc)
        first_col = "owner_first_name" if "owner_first_name" in df.columns else ("first_name" if "first_name" in df.columns else None)
        last_col = "owner_last_name" if "owner_last_name" in df.columns else ("last_name" if "last_name" in df.columns else None)

        if first_col and last_col:
            first = df[first_col].fillna("").astype(str).str.strip()
            last = df[last_col].fillna("").astype(str).str.strip()
            df["hubspot_owner_name"] = (first + " " + last).str.strip()
            # Filter to only our reps by last name
            logger.info("Emails: unique last names: %s", df[last_col].unique()[:20].tolist())
            df = df[df[last_col].astype(str).str.strip().isin(REP_LAST_NAMES)].copy()
        elif "activity_assigned_to" in df.columns:
            df["hubspot_owner_name"] = df["activity_assigned_to"].apply(lambda x: uid_map.get(_clean_uid(x), ""))
            df = df[df["hubspot_owner_name"] != ""].copy()
        else:
            logger.warning("Emails: no owner columns found. Available: %s", list(df.columns))
        logger.info("Emails owner mapping: %d rows after filtering to reps.", len(df))

    elif tab_type == "notes":
        # Notes have activity_assigned_to (UID) — map via uid_map
        if "activity_assigned_to" in df.columns:
            df["hubspot_owner_name"] = df["activity_assigned_to"].apply(lambda x: uid_map.get(_clean_uid(x), ""))
            df = df[df["hubspot_owner_name"] != ""].copy()
        logger.info("Notes owner mapping: %d rows after filtering to reps.", len(df))

    elif tab_type == "tickets":
        first = df.get("first_name", pd.Series("", index=df.index)).fillna("").astype(str).str.strip()
        last = df.get("last_name", pd.Series("", index=df.index)).fillna("").astype(str).str.strip()
        df["hubspot_owner_name"] = (first + " " + last).str.strip()

    # deals: hubspot_owner_name already set from Opp Owner alias
    return df


# -- Meeting Deduplication ------------------------------------------------

OUTCOME_PRIORITY = {
    "Completed": 5, "No Show": 4, "Canceled": 3,
    "Rescheduled": 2, "Scheduled": 1, "": 0
}


def _norm_meeting_name(name: str) -> str:
    """Strip [Gong] and Google Meet: prefixes."""
    n = str(name).strip() if pd.notna(name) else ""
    for prefix in ["[Gong] ", "[Gong]", "Google Meet: ", "Google Meet:"]:
        if n.startswith(prefix):
            n = n[len(prefix):]
    return n.strip()


def _safe_str(val) -> str:
    if pd.isna(val) or val is None:
        return ""
    return str(val).strip()


def _best_value(values: list[str]) -> str:
    """Return the longest non-empty string from a list."""
    non_empty = [v for v in values if v]
    return max(non_empty, key=len) if non_empty else ""


def deduplicate_meetings(df: pd.DataFrame) -> pd.DataFrame:
    """
    Deduplicate meetings using the three-pattern algorithm:
    1. [Gong] prefix duplicates
    2. Google Meet: prefix duplicates
    3. Blank-name CRM entries matching by date+rep+company

    Groups are merged keeping the richest data.
    """
    if df.empty:
        return df

    # Ensure we have the needed columns
    name_col = "meeting_name" if "meeting_name" in df.columns else None
    date_col = "meeting_start_time" if "meeting_start_time" in df.columns else "activity_date"
    rep_col = "hubspot_owner_name"
    company_col = "company_name"
    outcome_col = "meeting_outcome"

    if name_col is None or date_col not in df.columns:
        logger.warning("Cannot deduplicate meetings — missing columns.")
        return df

    # Parse dates to just date part for grouping
    df = df.copy()
    df["_start_date"] = pd.to_datetime(df[date_col], errors="coerce").dt.date

    # Normalize meeting names
    df["_norm_name"] = df[name_col].apply(_norm_meeting_name)

    # Check for Gong prefix
    raw_name = df[name_col].fillna("").astype(str)
    df["has_gong"] = raw_name.str.startswith("[Gong]")

    # Step 1 & 2: Group named meetings
    named_groups: dict[tuple, list[int]] = defaultdict(list)
    blank_indices: list[int] = []

    for idx in df.index:
        norm = df.at[idx, "_norm_name"]
        if norm:
            key = (
                norm,
                df.at[idx, "_start_date"],
                _safe_str(df.at[idx, rep_col]) if rep_col in df.columns else "",
            )
            named_groups[key].append(idx)
        else:
            blank_indices.append(idx)

    # Step 3: Match blanks to named groups by date+rep+company
    named_lookup: dict[tuple, tuple] = {}
    for key, indices in named_groups.items():
        for idx in indices:
            comp = _safe_str(df.at[idx, company_col]) if company_col in df.columns else ""
            if comp:
                lookup_key = (key[1], key[2], comp)  # date, rep, company
                named_lookup[lookup_key] = key

    for idx in blank_indices:
        rep = _safe_str(df.at[idx, rep_col]) if rep_col in df.columns else ""
        comp = _safe_str(df.at[idx, company_col]) if company_col in df.columns else ""
        date_val = df.at[idx, "_start_date"]
        lookup_key = (date_val, rep, comp)
        if lookup_key in named_lookup:
            named_groups[named_lookup[lookup_key]].append(idx)
        else:
            # Standalone blank — keep as its own group
            named_groups[("_blank", date_val, rep)].append(idx)

    # Step 4: Merge each group
    merged_rows = []
    merge_cols = [c for c in df.columns if not c.startswith("_")]

    for key, indices in named_groups.items():
        if len(indices) == 1:
            merged_rows.append(df.loc[indices[0], merge_cols].to_dict())
            continue

        group = df.loc[indices]
        merged = {}

        for col in merge_cols:
            if col == outcome_col:
                # Use highest priority outcome
                outcomes = group[col].fillna("").astype(str).tolist()
                best_outcome = max(outcomes, key=lambda o: OUTCOME_PRIORITY.get(o.strip(), 0))
                merged[col] = best_outcome
            elif col == "has_gong":
                merged[col] = group[col].any()
            elif col == name_col:
                # Use the normalized name (without prefixes)
                merged[col] = key[0] if key[0] != "_blank" else ""
            else:
                # Keep longest non-empty value
                vals = group[col].fillna("").astype(str).tolist()
                merged[col] = _best_value(vals)

        merged_rows.append(merged)

    result = pd.DataFrame(merged_rows)

    # Fix mixed types from merge — re-parse datetime columns
    for col in result.columns:
        if col in DATE_COLUMNS or col.endswith("_date") or col.endswith("_time") or col.endswith("_at"):
            result[col] = pd.to_datetime(result[col], errors="coerce")

    logger.info("Meeting dedup: %d -> %d rows (removed %d duplicates).",
                len(df), len(result), len(df) - len(result))
    return result


def deduplicate_emails(df: pd.DataFrame) -> pd.DataFrame:
    """
    Remove duplicate emails and collapse threads.
    
    Two-phase dedup:
      Phase 1: Remove Gong duplicates ([Gong Out]/[Gong In] copies of same email)
      Phase 2: Collapse email threads into single activity records.
               "Re: Re: Re: Subject" and "Re: Subject" on the same company = 1 thread.
               Keep the MOST RECENT email in the thread as the representative record.
               Store thread depth and all subjects for AI analysis.
    """
    if df.empty:
        return df

    pre = len(df)
    df = df.copy()

    subject_col = "email_subject" if "email_subject" in df.columns else None
    if subject_col is None:
        logger.warning("No email_subject column — skipping email dedup.")
        return df

    date_col = "activity_date" if "activity_date" in df.columns else "create_date"
    if date_col not in df.columns:
        logger.warning("No date column for email dedup.")
        return df

    # ── Phase 1: Remove Gong duplicates ──
    raw_subject = df[subject_col].fillna("").astype(str)
    df["_is_gong"] = raw_subject.str.contains(r'^\[Gong (Out|In)\]', regex=True)
    df["_clean_subject"] = raw_subject.str.replace(r'^\[Gong (Out|In)\]\s*', '', regex=True).str.strip()

    df["_email_date"] = pd.to_datetime(df[date_col], errors="coerce").dt.date
    co_col = "company_name" if "company_name" in df.columns else None
    df["_co"] = df[co_col].fillna("").astype(str).str.strip().str.lower() if co_col else ""
    from_col = "email_from_address" if "email_from_address" in df.columns else None
    df["_from"] = df[from_col].fillna("").astype(str).str.strip().str.lower() if from_col else ""

    has_subject = df["_clean_subject"].str.strip() != ""
    with_subject = df[has_subject].copy()
    without_subject = df[~has_subject].copy()

    if not with_subject.empty:
        with_subject = with_subject.sort_values("_is_gong", ascending=True)
        gong_group = ["_clean_subject", "_email_date", "_co", "_from"]
        with_subject = with_subject.drop_duplicates(subset=[c for c in gong_group if c in with_subject.columns], keep="first")

    df = pd.concat([with_subject, without_subject], ignore_index=True)
    after_gong = len(df)

    # ── Phase 2: Collapse email threads ──
    # Strip Re:/Fwd:/FW: prefixes to get root subject (the original thread topic)
    df["_thread_subject"] = (
        df["_clean_subject"]
        .str.replace(r'^(Re:\s*|Fwd:\s*|FW:\s*|Fw:\s*)+', '', regex=True)
        .str.strip()
        .str.lower()
    )

    # Group by thread subject + company (threads span multiple days)
    df["_dt"] = pd.to_datetime(df[date_col], errors="coerce")

    # Only collapse threads where we have a thread subject
    has_thread = df["_thread_subject"] != ""
    threadable = df[has_thread].copy()
    non_threadable = df[~has_thread].copy()

    if not threadable.empty:
        thread_group = ["_thread_subject", "_co"]
        # Sort by date desc so first record is the most recent
        threadable = threadable.sort_values("_dt", ascending=False)

        # For each thread group, keep the most recent email and annotate with thread info
        thread_records = []
        for key, group in threadable.groupby([c for c in thread_group if c in threadable.columns]):
            # Keep the most recent email as the representative
            rep_row = group.iloc[0].to_dict()
            thread_depth = len(group)
            rep_row["thread_depth"] = thread_depth

            # Build thread summary for AI analysis (all subjects + dates)
            if thread_depth > 1:
                thread_parts = []
                for _, msg in group.iterrows():
                    dt_str = msg["_dt"].strftime("%m/%d") if pd.notna(msg["_dt"]) else "?"
                    direction = msg.get("email_direction", "")
                    subj = msg.get("_clean_subject", "")[:80]
                    thread_parts.append(f"{dt_str} [{direction}] {subj}")
                rep_row["thread_summary"] = " | ".join(thread_parts)
            else:
                rep_row["thread_summary"] = ""

            thread_records.append(rep_row)

        collapsed = pd.DataFrame(thread_records)
    else:
        collapsed = threadable
        if "thread_depth" not in collapsed.columns:
            collapsed["thread_depth"] = 1
            collapsed["thread_summary"] = ""

    result = pd.concat([collapsed, non_threadable], ignore_index=True)

    # Add thread_depth to non-threadable
    if "thread_depth" not in result.columns:
        result["thread_depth"] = 1
    if "thread_summary" not in result.columns:
        result["thread_summary"] = ""
    result["thread_depth"] = result["thread_depth"].fillna(1).astype(int)

    # Clean up temp columns
    drop_cols = ["_is_gong", "_clean_subject", "_email_date", "_co", "_from",
                 "_thread_subject", "_dt"]
    result = result.drop(columns=[c for c in drop_cols if c in result.columns], errors="ignore")

    logger.info("Email dedup: %d -> %d after Gong dedup -> %d after thread collapse (removed %d total).",
                pre, after_gong, len(result), pre - len(result))
    return result


# -- Column dedup & normalization pipeline --------------------------------

def _deduplicate_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Append _2, _3 etc. to duplicate column names."""
    cols = list(df.columns)
    seen: dict[str, int] = {}
    new_cols = []
    for c in cols:
        if c in seen:
            seen[c] += 1
            new_cols.append(f"{c}_{seen[c]}")
        else:
            seen[c] = 1
            new_cols.append(c)
    df.columns = new_cols
    return df


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    df = df.copy()
    df.columns = [to_snake_case(c) for c in df.columns]
    df = _deduplicate_columns(df)
    df = df.rename(columns=COLUMN_ALIASES)
    df = df.loc[:, [bool(str(c).strip()) and not str(c).startswith("unnamed") for c in df.columns]]
    return df


def coerce_dates(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    df = df.copy()
    for col in df.columns:
        if col in DATE_COLUMNS or col.endswith("_date") or col.endswith("_time") or col.endswith("_at"):
            df[col] = pd.to_datetime(df[col], errors="coerce")
    return df


def coerce_numerics(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    df = df.copy()
    for col in df.columns:
        if col in NUMERIC_COLUMNS or col.endswith("_amount") or col.endswith("_duration"):
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def strip_whitespace(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    df = df.copy()
    for col in df.columns:
        if df[col].dtype != object:
            continue
        series = df[col]
        if isinstance(series, pd.DataFrame):
            series = series.iloc[:, 0]
        series = series.astype(str).str.strip()
        series = series.replace({"nan": np.nan, "": np.nan, "None": np.nan, "none": np.nan})
        df[col] = series
    return df


def safe_column(df: pd.DataFrame, col: str, default=np.nan) -> pd.Series:
    if col in df.columns:
        result = df[col]
        if isinstance(result, pd.DataFrame):
            result = result.iloc[:, 0]
        return result
    return pd.Series(default, index=df.index, name=col)


def normalize_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Full normalization: snake_case -> dedup cols -> alias -> whitespace -> dates -> numerics."""
    if df.empty:
        return df
    df = normalize_columns(df)
    df = strip_whitespace(df)
    df = coerce_dates(df)
    df = coerce_numerics(df)
    logger.info("Normalized: %d rows x %d cols.", len(df), len(df.columns))
    return df
