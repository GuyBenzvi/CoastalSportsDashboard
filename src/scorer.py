"""
scorer.py
---------
Applies sport condition scoring to processed DataFrames.

Scoring logic (confirmed with user):
  - Within [min_range, max_range]               → component_score = 1.0
  - Between boundary and extreme threshold       → linear decay 1.0 → 0.0
  - Beyond extreme threshold                     → component_score = 0.0
  - total_score = sum(weight * component_score) * 100  →  0–100 scale

Outputs:
  /data/processed/scores.parquet   — all hourly scored rows across all locations
  /data/processed/best_slots.parquet — best hour-slot per sport per location per day
"""

import logging
from pathlib import Path

import numpy as np
import pandas as pd

from src.sports import SPORTS, get_grade

logger = logging.getLogger(__name__)

PROCESSED_DIR = Path(__file__).parent.parent / "data" / "processed"
SPORT_NAMES = list(SPORTS.keys())


def _component_score(value: float, min_r: float, max_r: float, extreme: float) -> float:
    """
    Compute a single variable's component score in [0, 1].

    Rules:
      value in [min_r, max_r]             → 1.0
      value in (max_r, extreme]           → linear decay from 1.0 to 0.0
      value in [extreme_lo, min_r)        → linear decay from 0.0 at extreme_lo to 1.0 at min_r
                                            (only applies to lower-bound violations)
      value beyond extreme (either side)  → 0.0
    """
    if np.isnan(value):
        return 0.0

    # Handle lower extreme (below the lower boundary)
    # For most sports min_range == 0, so the lower extreme threshold is 0 itself
    # We treat negative-side extreme as: below (min_r - (extreme - max_r)) capped at 0
    # Simpler: if within range → 1.0; if beyond extreme → 0.0; else linear.
    if min_r <= value <= max_r:
        return 1.0

    if value < min_r:
        # How far below the lower boundary?
        lower_extreme = max(0.0, min_r - (extreme - max_r)) if extreme > max_r else 0.0
        if value <= lower_extreme:
            return 0.0
        if min_r == lower_extreme:
            return 0.0
        return (value - lower_extreme) / (min_r - lower_extreme)

    # value > max_r
    if value >= extreme:
        return 0.0
    return 1.0 - (value - max_r) / (extreme - max_r)


def score_sport(df: pd.DataFrame, sport_name: str) -> pd.Series:
    """
    Return a Series of 0–100 scores for each row in df for the given sport.
    """
    sport_cfg = SPORTS[sport_name]
    total = pd.Series(0.0, index=df.index)

    for col, params in sport_cfg["variables"].items():
        if col not in df.columns:
            logger.warning("Column %s missing for sport %s — skipping", col, sport_name)
            continue
        scores = df[col].apply(
            lambda v, p=params: _component_score(
                v, p["min_range"], p["max_range"], p["extreme"]
            )
        )
        total += params["weight"] * scores

    return (total * 100).clip(0, 100).round(2)


def score_all_locations(location_dfs: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    Score all sports for all locations and return a combined DataFrame.

    Parameters
    ----------
    location_dfs : dict slug → cleaned hourly DataFrame

    Returns
    -------
    Combined scored DataFrame with columns:
        slug, name, region, lat, lon, time,
        wind_speed_ms, wind_knots, wave_height_m, precipitation_mm,
        score_Kitesurf, score_Surfing, score_SUP,
        best_sport, best_score, grade_label, grade_color
    """
    all_rows = []

    for slug, df in location_dfs.items():
        if df.empty:
            logger.warning("Empty DataFrame for %s — skipping scoring", slug)
            continue

        scored = df.copy()

        for sport in SPORT_NAMES:
            scored[f"score_{sport}"] = score_sport(df, sport)

        score_cols = [f"score_{s}" for s in SPORT_NAMES]
        scored["best_sport"] = scored[score_cols].idxmax(axis=1).str.replace("score_", "", regex=False)
        scored["best_score"] = scored[score_cols].max(axis=1)
        grade_series = scored["best_score"].apply(get_grade)
        scored["grade_label"] = grade_series.apply(lambda x: x[0])
        scored["grade_color"] = grade_series.apply(lambda x: x[1])
        scored["slug"] = slug

        all_rows.append(scored)

    if not all_rows:
        logger.error("No scored data produced — all locations empty")
        return pd.DataFrame()

    combined = pd.concat(all_rows, ignore_index=True)
    out_path = PROCESSED_DIR / "scores.parquet"
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    combined.to_parquet(out_path, index=False)
    logger.info("Scores saved: %d rows → %s", len(combined), out_path)
    return combined


def compute_best_slots(scores_df: pd.DataFrame) -> pd.DataFrame:
    """
    For each sport × location × day, find the hour-slot with the highest score.

    Returns a DataFrame with columns:
        sport, date, slug, name, region, time (best hour), score, grade_label, grade_color
    """
    if scores_df.empty:
        return pd.DataFrame()

    scores_df = scores_df.copy()
    scores_df["date"] = pd.to_datetime(scores_df["time"]).dt.date

    rows = []
    for sport in SPORT_NAMES:
        score_col = f"score_{sport}"
        if score_col not in scores_df.columns:
            continue
        for (slug, date), group in scores_df.groupby(["slug", "date"]):
            best_idx = group[score_col].idxmax()
            best_row = group.loc[best_idx]
            grade_label, grade_color = get_grade(best_row[score_col])
            rows.append({
                "sport":       sport,
                "date":        date,
                "slug":        slug,
                "name":        best_row.get("name", slug),
                "region":      best_row.get("region", ""),
                "best_time":   pd.to_datetime(best_row["time"]),
                "score":       round(float(best_row[score_col]), 1),
                "grade_label": grade_label,
                "grade_color": grade_color,
            })

    best_df = pd.DataFrame(rows)
    if not best_df.empty:
        out_path = PROCESSED_DIR / "best_slots.parquet"
        best_df.to_parquet(out_path, index=False)
        logger.info("Best slots saved: %d rows → %s", len(best_df), out_path)
    return best_df
