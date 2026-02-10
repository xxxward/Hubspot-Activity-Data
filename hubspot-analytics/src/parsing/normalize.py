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
    logger.info("Meeting dedup: %d -> %d rows (removed %d duplicates).",
                len(df), len(result), len(df) - len(result))
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
