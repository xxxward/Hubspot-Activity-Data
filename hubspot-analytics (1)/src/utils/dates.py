"""
Date utilities: period bucketing, fiscal quarters, cycle length calculation.
"""

import os
from datetime import datetime

import pandas as pd
import pytz

TIMEZONE = pytz.timezone(os.getenv("TIMEZONE", "US/Eastern"))


def now_tz() -> datetime:
    """Current datetime in the configured timezone."""
    return datetime.now(TIMEZONE)


def current_quarter_range() -> tuple[pd.Timestamp, pd.Timestamp]:
    """Return (start, end) of the current calendar quarter."""
    today = now_tz()
    q_start_month = ((today.month - 1) // 3) * 3 + 1
    q_start = pd.Timestamp(year=today.year, month=q_start_month, day=1)
    q_end = (q_start + pd.offsets.QuarterEnd(1)).normalize()
    return q_start, q_end


def add_period_columns(df: pd.DataFrame, date_col: str) -> pd.DataFrame:
    """
    Add period_day, period_week (Monday start), period_month from a date column.
    """
    if df.empty or date_col not in df.columns:
        return df
    df = df.copy()
    dt = pd.to_datetime(df[date_col], errors="coerce")
    df["period_day"] = dt.dt.date
    df["period_week"] = dt.dt.to_period("W-MON").apply(
        lambda p: p.start_time.date() if pd.notna(p) else None
    )
    df["period_month"] = dt.dt.to_period("M").apply(
        lambda p: p.start_time.date() if pd.notna(p) else None
    )
    return df


def sales_cycle_days(created: pd.Series, closed: pd.Series) -> pd.Series:
    """Days between created and closed dates."""
    return (
        pd.to_datetime(closed, errors="coerce") - pd.to_datetime(created, errors="coerce")
    ).dt.days
