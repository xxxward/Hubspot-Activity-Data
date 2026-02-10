"""
Activity metrics: count calls, meetings, completed tasks, overdue tasks
by rep at daily / weekly / monthly grain.

Also builds a combined activity log for timeline views.

NOTE: Your spreadsheet has no dedicated Emails tab, so email counts
are omitted.  If an Emails tab is added later, pass it here and
it will be picked up automatically.
"""

import logging
from typing import Optional

import pandas as pd

from src.utils.dates import add_period_columns

logger = logging.getLogger(__name__)


# ── Column resolution helpers ───────────────────────────────────────

def _resolve_date_col(df: pd.DataFrame) -> Optional[str]:
    """Pick the best date column in an activity DataFrame."""
    for c in ("activity_date", "meeting_start_time", "created_date",
              "create_date", "timestamp", "date"):
        if c in df.columns:
            return c
    dt_cols = df.select_dtypes(include=["datetime64"]).columns
    return dt_cols[0] if len(dt_cols) else None


def _resolve_owner_col(df: pd.DataFrame) -> str:
    for c in ("hubspot_owner_name", "activity_assigned_to", "owner_name"):
        if c in df.columns:
            return c
    return "hubspot_owner_name"


# ── Internals ───────────────────────────────────────────────────────

def _count_by_rep_period(df: pd.DataFrame, period_col: str, value_name: str) -> pd.DataFrame:
    owner = _resolve_owner_col(df)
    if df.empty or period_col not in df.columns:
        return pd.DataFrame(columns=[owner, period_col, value_name])
    return (
        df.groupby([owner, period_col], dropna=False)
        .size()
        .reset_index(name=value_name)
    )


def _prepare(df: pd.DataFrame, activity_type: str) -> pd.DataFrame:
    """Identify date column, add period columns, tag activity type."""
    if df.empty:
        return df
    date_col = _resolve_date_col(df)
    if date_col is None:
        logger.warning("No date column for %s — skipping period bucketing.", activity_type)
        return df
    df = add_period_columns(df, date_col)
    df["activity_type"] = activity_type
    return df


def _split_tasks(tasks: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Split tasks into completed vs overdue.

    Logic:
      - 'Completed' task_status → completed
      - 'Overdue'/'Deferred' status → overdue
      - Not completed AND past due_date → overdue
    """
    if tasks.empty:
        return pd.DataFrame(), pd.DataFrame()

    tasks = _prepare(tasks, "task")

    # Find the status column
    status_col = None
    for c in ("task_status", "status", "hs_task_status"):
        if c in tasks.columns:
            status_col = c
            break

    if status_col is None:
        logger.warning("No task_status column — treating all tasks as completed.")
        return tasks, pd.DataFrame()

    upper = tasks[status_col].astype(str).str.upper().str.strip()
    completed_mask = upper.isin({"COMPLETED", "COMPLETE", "DONE"})

    # Overdue: explicit status OR past due_date + not completed
    overdue_mask = upper.isin({"OVERDUE", "PAST_DUE", "DEFERRED"})
    for c in ("due_date", "hs_task_due_date"):
        if c in tasks.columns:
            past_due = pd.to_datetime(tasks[c], errors="coerce") < pd.Timestamp.now()
            overdue_mask = overdue_mask | (past_due & ~completed_mask)
            break

    return tasks.loc[completed_mask].copy(), tasks.loc[overdue_mask].copy()


# ── Public API ──────────────────────────────────────────────────────

def count_activities(
    calls: pd.DataFrame,
    meetings: pd.DataFrame,
    tasks: pd.DataFrame,
    emails: pd.DataFrame | None = None,
) -> dict[str, pd.DataFrame]:
    """
    Count activities by rep at daily/weekly/monthly grain.

    Returns dict:
        activity_counts_daily
        activity_counts_weekly
        activity_counts_monthly
    """
    calls = _prepare(calls, "call")
    meetings = _prepare(meetings, "meeting")
    tasks_completed, tasks_overdue = _split_tasks(tasks)
    tasks_completed = _prepare(tasks_completed, "completed_task")
    tasks_overdue = _prepare(tasks_overdue, "overdue_task")

    email_df = pd.DataFrame()
    if emails is not None and not emails.empty:
        email_df = _prepare(emails, "email")

    result: dict[str, pd.DataFrame] = {}

    for label, period_col in [
        ("daily", "period_day"),
        ("weekly", "period_week"),
        ("monthly", "period_month"),
    ]:
        frames: list[pd.DataFrame] = []
        for df, metric in [
            (meetings, "meetings"),
            (calls, "calls"),
            (email_df, "emails"),
            (tasks_completed, "completed_tasks"),
            (tasks_overdue, "overdue_tasks"),
        ]:
            counted = _count_by_rep_period(df, period_col, metric)
            if not counted.empty:
                frames.append(counted)

        if not frames:
            result[f"activity_counts_{label}"] = pd.DataFrame()
            continue

        owner = _resolve_owner_col(frames[0])
        merged = frames[0]
        for f in frames[1:]:
            merged = pd.merge(merged, f, on=[owner, period_col], how="outer")

        metric_cols = ["meetings", "calls", "emails", "completed_tasks", "overdue_tasks"]
        for mc in metric_cols:
            if mc in merged.columns:
                merged[mc] = merged[mc].fillna(0).astype(int)
            else:
                merged[mc] = 0

        result[f"activity_counts_{label}"] = merged

    return result


def build_combined_activity_log(
    calls: pd.DataFrame,
    meetings: pd.DataFrame,
    tasks: pd.DataFrame,
    emails: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Single combined activity log — one row per activity."""
    frames = []
    for df, atype in [(calls, "call"), (meetings, "meeting"), (tasks, "task")]:
        if not df.empty:
            tmp = df.copy()
            tmp["activity_type"] = atype
            frames.append(tmp)
    if emails is not None and not emails.empty:
        tmp = emails.copy()
        tmp["activity_type"] = "email"
        frames.append(tmp)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
