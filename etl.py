"""
etl.py
------
Main ETL entry point for the Thailand Coastal Sports Dashboard.

Usage:
    python etl.py            # normal run (uses 1-hour cache)
    python etl.py --refresh  # force re-fetch from API

Outputs:
    /data/raw/<slug>_weather.json
    /data/raw/<slug>_marine.json
    /data/processed/<slug>_processed.parquet
    /data/processed/scores.parquet
    /data/processed/best_slots.parquet
    /data/processed/quality_report.json
"""

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

from src.fetcher import fetch_weather, fetch_marine
from src.locations import LOCATIONS
from src.scorer import compute_best_slots, score_all_locations
from src.transformer import transform_location

# ── Logging setup ──────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("etl")

PROCESSED_DIR = Path("data") / "processed"


def run_etl(force_refresh: bool = False) -> dict:
    """
    Execute the full ETL pipeline for all locations.

    Returns the quality report dict.
    """
    logger.info("=" * 60)
    logger.info("Thailand Coastal Sports Dashboard — ETL start")
    logger.info("Force refresh: %s", force_refresh)
    logger.info("=" * 60)

    quality_report = {
        "run_at": datetime.now(timezone.utc).isoformat(),
        "force_refresh": force_refresh,
        "locations": [],
        "errors": [],
    }

    location_dfs = {}

    for loc in LOCATIONS:
        slug = loc["slug"]
        name = loc["name"]
        lat, lon = loc["lat"], loc["lon"]

        logger.info("Processing: %s", name)

        # ── Fetch ──────────────────────────────────────────────────────────
        try:
            weather_raw = fetch_weather(slug, lat, lon, force=force_refresh)
        except Exception as exc:
            err = f"{name}: weather fetch failed — {exc}"
            logger.error(err)
            quality_report["errors"].append(err)
            continue

        try:
            marine_raw = fetch_marine(slug, lat, lon, force=force_refresh)
        except Exception as exc:
            err = f"{name}: marine fetch failed — {exc}"
            logger.error(err)
            quality_report["errors"].append(err)
            continue

        # ── Transform + QC ────────────────────────────────────────────────
        try:
            df, qc = transform_location(slug, weather_raw, marine_raw)
        except Exception as exc:
            err = f"{name}: transform failed — {exc}"
            logger.error(err)
            quality_report["errors"].append(err)
            continue

        # Attach location metadata to the DataFrame for the scorer
        df["name"]   = name
        df["region"] = loc["region"]
        df["lat"]    = lat
        df["lon"]    = lon

        location_dfs[slug] = df
        quality_report["locations"].append(qc)

        if qc.get("issues"):
            logger.warning("%s QC issues: %s", name, qc["issues"])

    # ── Score ──────────────────────────────────────────────────────────────
    if not location_dfs:
        logger.error("No location data available — ETL aborted")
        quality_report["errors"].append("All locations failed; no data produced")
    else:
        logger.info("Scoring %d locations…", len(location_dfs))
        scores_df  = score_all_locations(location_dfs)
        _           = compute_best_slots(scores_df)
        logger.info("Scoring complete.")

    # ── Persist quality report ─────────────────────────────────────────────
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    qr_path = PROCESSED_DIR / "quality_report.json"
    with open(qr_path, "w", encoding="utf-8") as f:
        json.dump(quality_report, f, indent=2, default=str)
    logger.info("Quality report saved → %s", qr_path)

    # ── Summary ────────────────────────────────────────────────────────────
    total_rows = sum(
        loc_qc.get("rows_final", 0) for loc_qc in quality_report["locations"]
    )
    total_dropped = sum(
        loc_qc.get("rows_dropped_outliers", 0) for loc_qc in quality_report["locations"]
    )
    logger.info("=" * 60)
    logger.info(
        "ETL complete: %d/%d locations, %d rows, %d dropped",
        len(location_dfs), len(LOCATIONS), total_rows, total_dropped,
    )
    if quality_report["errors"]:
        logger.warning("%d errors encountered — see quality_report.json", len(quality_report["errors"]))
    logger.info("=" * 60)

    return quality_report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Thailand Coastal Sports Dashboard ETL")
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Force re-fetch from API even if cache is fresh",
    )
    args = parser.parse_args()

    report = run_etl(force_refresh=args.refresh)

    # Exit with error code if any location failed
    if report.get("errors"):
        sys.exit(1)
