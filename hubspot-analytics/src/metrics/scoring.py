"""
Composite activity score per rep.

Formula (no emails tab currently):
    meetings × 5  +  calls × 3  +  completed_tasks × 2  +  overdue_tasks × (−2)

If an emails column appears later it will be weighted × 1.
"""

import logging

import pandas as pd

logger = logging.getLogger(__name__)

WEIGHTS: dict[str, int] = {
    "meetings": 5,
    "calls": 3,
    "emails": 1,
    "completed_tasks": 2,
    "overdue_tasks": -2,
}


def _ensure_metric_cols(df: pd.DataFrame) -> pd.DataFrame:
    for mc in WEIGHTS:
        if mc not in df.columns:
            df[mc] = 0
    return df


def compute_activity_score(
    activity_counts: pd.DataFrame,
    owner_col: str = "hubspot_owner_name",
) -> pd.DataFrame:
    """
    Total activity score per rep (summed across all periods).

    Returns one row per rep: rep | meetings | calls | … | activity_score
    """
    if activity_counts.empty:
        return pd.DataFrame(columns=[owner_col] + list(WEIGHTS) + ["activity_score"])

    # Resolve owner col
    if owner_col not in activity_counts.columns:
        for c in ("owner_name", "activity_assigned_to"):
            if c in activity_counts.columns:
                owner_col = c
                break

    df = _ensure_metric_cols(activity_counts.copy())
    totals = df.groupby(owner_col, dropna=False).agg(
        {mc: "sum" for mc in WEIGHTS}
    ).reset_index()

    totals["activity_score"] = sum(totals[c] * w for c, w in WEIGHTS.items())
    return totals.sort_values("activity_score", ascending=False).reset_index(drop=True)


def compute_activity_score_by_period(
    activity_counts: pd.DataFrame,
    period_col: str = "period_week",
    owner_col: str = "hubspot_owner_name",
) -> pd.DataFrame:
    """Activity score per rep per period (for trend charts)."""
    if activity_counts.empty or period_col not in activity_counts.columns:
        return pd.DataFrame(columns=[owner_col, period_col, "activity_score"])

    df = _ensure_metric_cols(activity_counts.copy())
    df["activity_score"] = sum(df[c] * w for c, w in WEIGHTS.items())
    return (
        df.groupby([owner_col, period_col], dropna=False)["activity_score"]
        .sum()
        .reset_index()
    )
