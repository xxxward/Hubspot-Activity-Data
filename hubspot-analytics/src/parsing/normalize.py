"""
Column normalization: snake_case conversion, alias mapping to canonical names,
date/numeric coercion, whitespace cleanup.

The COLUMN_ALIASES dict maps raw Coefficient column names (after snake_case)
to the canonical internal names used throughout the codebase.
"""

import re
import logging

import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)

# ── snake_case helper ───────────────────────────────────────────────

def to_snake_case(name: str) -> str:
    s = re.sub(r"[\s\-\.\/\(\)]+", "_", str(name).strip())
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s)
    s = re.sub(r"_+", "_", s).lower().strip("_")
    return s


# ── Column alias map ────────────────────────────────────────────────
# Keys   = snake_case of the raw Coefficient header
# Values = canonical internal name
#
# Only columns that need renaming are listed.  Columns whose snake_case
# form already matches the canonical name (e.g. "amount") are omitted.

COLUMN_ALIASES: dict[str, str] = {
    # ── Deals tab ──
    "deal_id": "deal_id",
    "deal_name": "deal_name",
    "first_name": "first_name",
    "last_name": "last_name",
    "create_date": "created_date",
    "close_date": "close_date",
    "deal_stage": "deal_stage",
    "is_deal_closed": "is_deal_closed",
    "is_closed_won": "is_closed_won",
    "forecast_category": "forecast_category",
    "forecast_probability": "forecast_probability",
    "deal_owner_email": "deal_owner_email",
    "billing_type": "billing_type",
    "deal_type": "deal_type",
    "associated_company_name": "company_name",
    "industry": "industry",
    "state_region": "state_region",
    "country_region": "country_region",
    "original_source_type": "original_source_type",
    "latest_traffic_source": "latest_traffic_source",
    "next_step": "next_step",
    "hub_spot_team": "hubspot_team",
    "hubspot_team": "hubspot_team",
    "opp_age": "opp_age",
    "opp_owner": "hubspot_owner_name",
    "sales_team": "sales_team",
    "opp_type_no_blanks": "opp_type",
    "hubspot_opp_url": "hubspot_opp_url",
    "opp_name_hyperlinked": "opp_name_hyperlinked",
    "pipeline": "pipeline",

    # ── Meetings tab ──
    "activity_date": "activity_date",
    "body_preview_truncated": "body_preview",
    "meeting_start_time": "meeting_start_time",
    "meeting_end_time": "meeting_end_time",
    "meeting_name": "meeting_name",
    "call_and_meeting_type": "call_and_meeting_type",
    "meeting_source": "meeting_source",
    "email": "email",
    "company_name": "company_name",
    "type": "type",
    "company_id": "company_id",
    "meeting_outcome": "meeting_outcome",
    "activity_assigned_to": "hubspot_owner_name",
    "activity_created_by": "activity_created_by",
    "follow_up_action": "follow_up_action",
    "create_date": "created_date",

    # ── Tasks tab ──
    "for_object_type": "for_object_type",
    "completed_at": "completed_at",
    "task_title": "task_title",
    "due_date": "due_date",
    "task_status": "task_status",
    "source": "source",
    "notes_preview": "notes_preview",
    "created_at": "created_date",
    "priority": "priority",
    "task_type": "task_type",
    "full_name": "full_name",
    "last_modified_at": "last_modified_date",

    # ── Calls tab ──
    "call_id": "call_id",
    "call_outcome": "call_outcome",
    "call_duration": "call_duration",
    "last_modified_date": "last_modified_date",
    "call_title": "call_title",
    "call_notes": "call_notes",
    "call_status": "call_status",
    "call_direction": "call_direction",
    "call_summary": "call_summary",
    "company_owner": "company_owner",

    # ── Tickets tab ──
    "ticket_id": "ticket_id",
    "ticket_name": "ticket_name",
    "ticket_status": "ticket_status",
    "ticket_description": "ticket_description",
    "deal_owner": "deal_owner",
    "first_name_ticket_owner": "ticket_owner_first_name",
}


# ── Date & numeric detection ───────────────────────────────────────

DATE_COLUMNS = {
    "created_date", "close_date", "activity_date", "meeting_start_time",
    "meeting_end_time", "completed_at", "due_date", "last_modified_date",
    "create_date", "created_at", "last_activity_date", "next_activity_date",
}

NUMERIC_COLUMNS = {
    "amount", "deal_id", "company_id", "call_duration", "ticket_id",
    "opp_age", "forecast_probability", "call_id",
}


# ── Public API ──────────────────────────────────────────────────────

def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Rename all columns to snake_case, then apply alias mapping."""
    if df.empty:
        return df
    df = df.copy()
    df.columns = [to_snake_case(c) for c in df.columns]
    df = df.rename(columns=COLUMN_ALIASES)
    # Drop unnamed columns
    df = df.loc[:, ~df.columns.str.match(r"^unnamed")]
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
    for col in df.select_dtypes(include=["object"]).columns:
        df[col] = df[col].astype(str).str.strip()
        df[col] = df[col].replace({"nan": np.nan, "": np.nan, "None": np.nan, "none": np.nan})
    return df


def safe_column(df: pd.DataFrame, col: str, default=np.nan) -> pd.Series:
    """Return a column if present, else a constant Series."""
    if col in df.columns:
        return df[col]
    return pd.Series(default, index=df.index, name=col)


def normalize_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """
    Full normalization pipeline:
      1. snake_case + alias mapping
      2. strip whitespace
      3. coerce dates
      4. coerce numerics
    """
    if df.empty:
        return df
    df = normalize_columns(df)
    df = strip_whitespace(df)
    df = coerce_dates(df)
    df = coerce_numerics(df)
    logger.info("Normalized: %d rows × %d cols.  Columns: %s",
                len(df), len(df.columns), list(df.columns))
    return df
