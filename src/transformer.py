"""
transformer.py
--------------
Merges raw weather + marine data, applies quality checks,
filters to the 05:00–19:00 window, and persists processed parquet files.

Quality checks performed:
  1. Missing value detection
  2. Duplicate timestamp detection
  3. Out-of-range / outlier removal:
       wind_speed_ms  < 0  or > 103 m/s  (~200 knots)
       wave_height_m  < 0  or > 20 m
       precipitation  < 0  or > 500 mm
"""

import logging
from pathlib import Path

import numpy as np
import pandas as pd

from src.sports import MS_TO_KNOTS

logger = logging.getLogger(__name__)

PROCESSED_DIR = Path(__file__).parent.parent / "data" / "processed"

# Valid value ranges (raw units from API)
VALID_RANGES = {
    "wind_speed_ms":   (0.0, 103.0),   # m/s  — ≈200 knots upper bound
    "wave_height_m":   (0.0,  20.0),   # metres
    "precipitation_mm":(0.0, 500.0),   # mm/h
}

# Day-use window in local Bangkok time (UTC+7)
WINDOW_START_HOUR = 5   # 05:00
WINDOW_END_HOUR   = 19  # 19:00 (inclusive)


def _parse_hourly(raw: dict, col_map: dict) -> pd.DataFrame:
    """
    Parse an Open-Meteo hourly response dict into a DataFrame.
    col_map maps the API column names to our internal names.
    """
    hourly = raw.get("hourly", {})
    times  = hourly.get("time", [])
    df = pd.DataFrame({"time": pd.to_datetime(times)})
    for api_col, our_col in col_map.items():
        values = hourly.get(api_col, [None] * len(times))
        df[our_col] = values
    return df


def transform_location(
    slug: str,
    weather_raw: dict,
    marine_raw: dict,
) -> tuple[pd.DataFrame, dict]:
    """
    Transform raw API data for one location into a clean hourly DataFrame.

    Returns:
        df          — cleaned hourly DataFrame
        qc_report   — dict with quality-check statistics
    """
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    qc: dict = {"slug": slug, "issues": []}

    # ── 1. Parse raw responses ──────────────────────────────────────────────
    weather_df = _parse_hourly(
        weather_raw,
        {"wind_speed_10m": "wind_speed_ms", "precipitation": "precipitation_mm"},
    )
    marine_df = _parse_hourly(
        marine_raw,
        {"wave_height": "wave_height_m"},
    )

    rows_weather = len(weather_df)
    rows_marine  = len(marine_df)
    qc["rows_fetched_weather"] = rows_weather
    qc["rows_fetched_marine"]  = rows_marine

    # ── 2. Merge on time ────────────────────────────────────────────────────
    if marine_raw.get("_marine_unavailable"):
        logger.warning("%s: Marine API unavailable — wave_height set to 0", slug)
        df = weather_df.copy()
        df["wave_height_m"] = 0.0
        qc["issues"].append("Marine API unavailable; wave_height defaulted to 0")
    else:
        df = pd.merge(weather_df, marine_df, on="time", how="inner")

    qc["rows_after_merge"] = len(df)

    # ── 3. Duplicate timestamp detection ───────────────────────────────────
    dups = df.duplicated(subset=["time"]).sum()
    if dups:
        qc["issues"].append(f"{dups} duplicate timestamps removed")
        df = df.drop_duplicates(subset=["time"])

    # ── 4. Missing value detection ─────────────────────────────────────────
    missing_counts = df[["wind_speed_ms", "wave_height_m", "precipitation_mm"]].isna().sum().to_dict()
    if any(v > 0 for v in missing_counts.values()):
        qc["issues"].append(f"Missing values detected: {missing_counts}")
        # Forward-fill then back-fill (short gaps in forecast are usually carry-overs)
        df[["wind_speed_ms", "wave_height_m", "precipitation_mm"]] = (
            df[["wind_speed_ms", "wave_height_m", "precipitation_mm"]]
            .ffill()
            .bfill()
        )
    qc["missing_before_fill"] = missing_counts

    # ── 5. Out-of-range / outlier removal ──────────────────────────────────
    rows_before = len(df)
    for col, (lo, hi) in VALID_RANGES.items():
        if col not in df.columns:
            continue
        out_mask = (df[col] < lo) | (df[col] > hi)
        n_out = out_mask.sum()
        if n_out:
            qc["issues"].append(f"{col}: {n_out} rows outside valid range [{lo}, {hi}] removed")
            df = df[~out_mask]
    qc["rows_dropped_outliers"] = rows_before - len(df)

    # ── 6. Time window filter (05:00–19:00 local Bangkok = UTC+7) ──────────
    # Open-Meteo returns times in the requested timezone already
    df["hour"] = df["time"].dt.hour
    df = df[(df["hour"] >= WINDOW_START_HOUR) & (df["hour"] <= WINDOW_END_HOUR)]
    df = df.drop(columns=["hour"])
    qc["rows_after_window_filter"] = len(df)

    # ── 7. Derived column: wind in knots (for scoring + display) ───────────
    df["wind_knots"] = df["wind_speed_ms"] * MS_TO_KNOTS

    # ── 8. Persist ─────────────────────────────────────────────────────────
    out_path = PROCESSED_DIR / f"{slug}_processed.parquet"
    df = df.reset_index(drop=True)
    df.to_parquet(out_path, index=False)
    logger.info("%s: %d rows saved to %s", slug, len(df), out_path)
    qc["rows_final"] = len(df)

    return df, qc
