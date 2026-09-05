"""
fetcher.py
----------
Fetches weather and marine data from Open-Meteo APIs.
Caches raw JSON responses in /data/raw/ with a 1-hour TTL.
"""

import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

RAW_DIR = Path(__file__).parent.parent / "data" / "raw"
CACHE_TTL_SECONDS = 3600  # 1 hour

WEATHER_API_URL = "https://api.open-meteo.com/v1/forecast"
MARINE_API_URL  = "https://marine-api.open-meteo.com/v1/marine"

WEATHER_PARAMS = {
    "hourly": "wind_speed_10m,precipitation",
    "wind_speed_unit": "ms",           # always fetch in m/s; we convert later
    "forecast_days": 7,
    "timezone": "Asia/Bangkok",
}

MARINE_PARAMS = {
    "hourly": "wave_height",
    "forecast_days": 7,
    "timezone": "Asia/Bangkok",
}


def _cache_path(slug: str, kind: str) -> Path:
    """Return the cache file path for a given location and data kind."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    return RAW_DIR / f"{slug}_{kind}.json"


def _is_cache_fresh(path: Path) -> bool:
    """Return True if the cache file exists and is younger than CACHE_TTL_SECONDS."""
    if not path.exists():
        return False
    age = time.time() - path.stat().st_mtime
    return age < CACHE_TTL_SECONDS


def _fetch_with_retry(url: str, params: dict, max_retries: int = 3) -> dict:
    """
    Fetch JSON from a URL with retry logic.
    Raises requests.HTTPError or RuntimeError on persistent failure.
    """
    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.get(url, params=params, timeout=15)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.Timeout:
            logger.warning("Timeout on attempt %d/%d for %s", attempt, max_retries, url)
        except requests.exceptions.HTTPError as exc:
            logger.error("HTTP error %s for %s", exc.response.status_code, url)
            raise
        except requests.exceptions.RequestException as exc:
            logger.warning("Request error on attempt %d/%d: %s", attempt, max_retries, exc)
        if attempt < max_retries:
            time.sleep(2 ** attempt)  # exponential back-off: 2s, 4s
    raise RuntimeError(f"Failed to fetch {url} after {max_retries} attempts")


def fetch_weather(slug: str, lat: float, lon: float, force: bool = False) -> dict:
    """
    Return raw weather JSON for a location.
    Uses cache unless force=True or cache is stale.
    """
    cache = _cache_path(slug, "weather")
    if not force and _is_cache_fresh(cache):
        logger.debug("Cache hit for %s weather", slug)
        with open(cache, "r", encoding="utf-8") as f:
            return json.load(f)

    logger.info("Fetching weather for %s (lat=%.4f, lon=%.4f)", slug, lat, lon)
    params = {**WEATHER_PARAMS, "latitude": lat, "longitude": lon}
    data = _fetch_with_retry(WEATHER_API_URL, params)
    data["_fetched_at"] = datetime.now(timezone.utc).isoformat()
    with open(cache, "w", encoding="utf-8") as f:
        json.dump(data, f)
    return data


def fetch_marine(slug: str, lat: float, lon: float, force: bool = False) -> dict:
    """
    Return raw marine JSON for a location.
    Uses cache unless force=True or cache is stale.
    """
    cache = _cache_path(slug, "marine")
    if not force and _is_cache_fresh(cache):
        logger.debug("Cache hit for %s marine", slug)
        with open(cache, "r", encoding="utf-8") as f:
            return json.load(f)

    logger.info("Fetching marine for %s (lat=%.4f, lon=%.4f)", slug, lat, lon)
    params = {**MARINE_PARAMS, "latitude": lat, "longitude": lon}
    try:
        data = _fetch_with_retry(MARINE_API_URL, params)
    except requests.exceptions.HTTPError as exc:
        # Marine API has limited coverage; land-locked coords return 400
        logger.warning(
            "Marine API unavailable for %s (%s). Wave height will be set to 0.",
            slug, exc,
        )
        # Build a synthetic zero-wave response so the pipeline continues
        data = {"hourly": {"time": [], "wave_height": []}, "_marine_unavailable": True}
    data["_fetched_at"] = datetime.now(timezone.utc).isoformat()
    with open(cache, "w", encoding="utf-8") as f:
        json.dump(data, f)
    return data
