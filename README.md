# 🌊 Thailand Coastal Sports Dashboard

A real-time weather and marine data pipeline + interactive Streamlit dashboard for water-sports enthusiasts along the Thai coastline. The dashboard surfaces 7-day forecasts for 11 coastal locations across the Gulf of Thailand and the Andaman Sea, scoring each location per sport (Kitesurf, Surfing, SUP) so athletes and travelers can instantly find the best time and place for their activity.

Weather data is fetched from [Open-Meteo](https://open-meteo.com/) — a **free, keyless, open-source** weather and marine forecast API.

---

## 🚀 Quick Start

```bash
git clone <repository-url>
cd <repository-folder>
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python etl.py
streamlit run app.py
```

No API keys. No Docker. No external databases. Just clone, install, run.

---

## 🌐 API Selection

**API:** [Open-Meteo](https://open-meteo.com/) — Weather Forecast API + Marine API

**Why this API:**
- Completely free and keyless — no account or token required.
- Provides hourly wind, precipitation, and wave-height forecasts up to 7 days.
- Covers all 11 Thai coastal locations accurately (ERA5 + GFS model blend).
- JSON responses, reliable uptime, and a permissive open-data license.
- Marine API provides wave height directly — no secondary data join needed.

**Endpoints used:**
- `https://api.open-meteo.com/v1/forecast` — wind speed (m/s), precipitation (mm/h)
- `https://marine-api.open-meteo.com/v1/marine` — wave height (m)

Both endpoints accept `latitude`, `longitude`, `forecast_days=7`, and `timezone=Asia/Bangkok`.

---

## 📐 Project Architecture

```
.
├── app.py                     # Streamlit dashboard (3 screens)
├── etl.py                     # ETL entry point
├── requirements.txt
├── README.md
├── start.ps1                  # One-command Windows launcher
├── src/
│   ├── locations.py           # 11 Thai coastal locations (lat/lon/region)
│   ├── sports.py              # Sport thresholds, weights, grade tiers, unit conversion
│   ├── fetcher.py             # Open-Meteo API client (1-hour TTL cache + retry)
│   ├── transformer.py         # Merge, quality-check, time-window filter, normalize
│   └── scorer.py              # Weighted sport scoring + best-slot aggregation
├── data/
│   ├── raw/                   # Cached JSON responses per location (1-hour TTL)
│   └── processed/             # Parquet analytical outputs + quality_report.json
├── ai_transcript/
│   └── transcript.md          # Full AI conversation log
└── tests/
    └── test_scorer.py         # Unit tests for scoring logic
```

---

## 🗄️ Data Model & ETL Explanation

### ETL Flow

```
Open-Meteo Weather API  ──┐
                           ├──► fetcher.py (cache) ──► transformer.py (QC + merge) ──► scorer.py ──► Parquet
Open-Meteo Marine API  ───┘
```

### Step-by-step

| Step | Module | Description |
|---|---|---|
| **Extract** | `src/fetcher.py` | Fetch hourly JSON for each location. Cache to `/data/raw/` for 1 hour to avoid redundant API calls. Retry up to 3× with exponential back-off. |
| **Transform** | `src/transformer.py` | Parse JSON → DataFrame, merge weather + marine on timestamp, apply QC (see below), filter to 05:00–19:00 Bangkok local time, convert wind from m/s → knots. |
| **Score** | `src/scorer.py` | Apply weighted sport scoring per row; compute best sport per hour; aggregate best hour-slot per sport × location × day. |
| **Load** | `etl.py` | Persist processed Parquet files and quality report JSON. |

### Processed Data Schema

**`data/processed/scores.parquet`** — 1 row per location per hour:

| Column | Type | Description |
|---|---|---|
| `time` | datetime | Forecast hour (Bangkok local, no tz info) |
| `slug` | str | Location identifier |
| `name` | str | Human-readable location name |
| `region` | str | Gulf of Thailand / Andaman Sea |
| `lat`, `lon` | float | Coordinates |
| `wind_speed_ms` | float | Wind speed in m/s (raw API unit) |
| `wind_knots` | float | Wind speed converted to knots (used for scoring) |
| `wave_height_m` | float | Significant wave height in metres |
| `precipitation_mm` | float | Precipitation in mm/h |
| `score_Kitesurf` | float | 0–100 score |
| `score_Surfing` | float | 0–100 score |
| `score_SUP` | float | 0–100 score |
| `best_sport` | str | Sport with highest score at this hour |
| `best_score` | float | Highest of the three sport scores |
| `grade_label` | str | Optimal / Good / Caution / Dangerous |
| `grade_color` | str | Hex color for the grade |

**`data/processed/best_slots.parquet`** — 1 row per sport × location × day (best hour):

| Column | Type | Description |
|---|---|---|
| `sport` | str | Kitesurf / Surfing / SUP |
| `date` | date | Forecast date |
| `slug`, `name`, `region` | str | Location info |
| `best_time` | datetime | Best hour for this sport on this day |
| `score` | float | Score at best hour |
| `grade_label`, `grade_color` | str | Grade info |

---

## 🗺️ Locations Covered

| Location | Region | Lat | Lon |
|---|---|---|---|
| Koh Phangan – Ban Tai (South) | Gulf of Thailand | 9.7022 | 100.0245 |
| Koh Phangan – Chaloklum (North) | Gulf of Thailand | 9.7891 | 100.0075 |
| Koh Phangan – Haad Yao / Sri Thanu (West) | Gulf of Thailand | 9.7620 | 99.9620 |
| Koh Phangan – Thong Nai Pan (East) | Gulf of Thailand | 9.7745 | 100.0550 |
| Hua Hin – Pranburi | Gulf of Thailand | 12.5684 | 99.9577 |
| Koh Samui – Chaweng | Gulf of Thailand | 9.5300 | 100.0650 |
| Koh Samui – Lipa Noi | Gulf of Thailand | 9.5100 | 99.9330 |
| Phuket – Kata Beach | Andaman Sea | 7.8206 | 98.2987 |
| Phuket – Nai Harn | Andaman Sea | 7.7770 | 98.3060 |
| Phuket – Nai Yang | Andaman Sea | 8.0930 | 98.2965 |
| Krabi – Railay | Andaman Sea | 8.0120 | 98.8375 |

---

## 🏄 Sports & Scoring

### Sport Thresholds & Weights

| Variable | Kitesurf | Surfing | SUP |
|---|---|---|---|
| **Wind** (knots) | 12–30 (wt 70%) | 5–20 (wt 10%) | 0–3 (wt 20%) |
| **Wave** (m) | 0–1 (wt 20%) | 1–3 (wt 80%) | 0–0.2 (wt 50%) |
| **Precip** (mm) | 0–10 (wt 10%) | 0–10 (wt 10%) | 0–5 (wt 30%) |

### Extreme Condition Limits (score forced to 0)

| Sport | Wind | Wave | Precip |
|---|---|---|---|
| Kitesurf | > 40 knots | > 4 m | > 20 mm |
| Surfing | > 25 knots | > 6 m | > 20 mm |
| SUP | > 20 knots | > 2 m | > 20 mm |

### Scoring Formula

For each variable independently:
- **In optimal range** → component score = 1.0
- **Between boundary and extreme threshold** → linear decay from 1.0 → 0.0
- **Below lower boundary** → linear decay from 0.0 (at zero) to 1.0 (at min_range)
- **Beyond extreme threshold** → component score = 0.0

```
total_score = Σ(weight × component_score) × 100   →  0–100
```

### Grade Labels

| Score | Label | Color |
|---|---|---|
| 76–100 | Optimal | 🟢 Green |
| 51–75 | Good | 🟡 Light Green |
| 26–50 | Caution | 🟠 Yellow |
| 0–25 | Dangerous | 🔴 Red |

---

## 📊 Dashboard Screens

### Screen 1 — Interactive Map
- Folium map of Thailand coastline with all 11 locations.
- **Hour selector** (05:00–19:00 Bangkok time): view any forecast slot; defaults to the current hour (or next-day 09:00 if after 19:00).
- Marker color = best sport at the selected hour (Kitesurf=Blue, Surfing=Orange, SUP=Green).
- Click any marker for a popup with sport, score, and grade.
- Summary cards below the map showing the average score and top-scoring location per sport.

### Screen 2 — Location Detail
- Select any of the 11 locations.
- Current conditions panel: wind, wave height, precipitation, best sport + grade badge.
- Hourly time-series charts (7-day horizon) for wind, wave height, and precipitation — with **optimal range bands** overlaid per sport.
- Combined sport score chart with grade-level horizontal bands (Optimal / Good / Caution / Dangerous).
- Unit switching: wind (knots / km/h / m/s / mph), wave height (meters / feet).

### Screen 3 — Best Spots
- Sport tabs (Kitesurf / Surfing / SUP).
- Top 3 locations per day ranked by score, with medal icons 🥇🥈🥉, best hour, and score.
- Score heatmap across all 11 locations × 7 forecast days for at-a-glance comparison.

---

## 🔍 Data Quality Checks

The ETL (`etl.py`) applies the following checks in `src/transformer.py`:

| Check | Action |
|---|---|
| Duplicate timestamps | Drop duplicates, log count |
| Missing values (NaN) | Forward-fill → back-fill; flagged in quality report |
| Wind speed < 0 or > 103 m/s (~200 knots) | Remove row |
| Wave height < 0 or > 20 m | Remove row |
| Precipitation < 0 or > 500 mm | Remove row |
| Time outside 05:00–19:00 local | Filter out (sports window only) |
| Marine API unavailable (HTTP 400) | Default wave_height to 0.0, log warning |

All issues are persisted to `data/processed/quality_report.json` and surfaced in the sidebar **Data Quality Report** expander in the Streamlit app.

---

## 🔄 ETL Notes

- **Cache TTL**: Raw API responses cached for 1 hour in `/data/raw/`. Re-fetched automatically when stale.
- **Force refresh**: `python etl.py --refresh` ignores cache and re-fetches all locations.
- **Auto-trigger**: The Streamlit app automatically runs ETL on startup if processed data is missing or older than 1 hour.
- **Fault isolation**: Each location is processed independently — a failure for one does not abort the others.

---

## 🤖 AI Usage

This project was built using an AI coding assistant (Antigravity / Claude Sonnet). The full conversation transcript is in `/ai_transcript/transcript.md`.

**How the assignment was broken down:**
The AI was used to analyse `Workflow.md` and the assignment docx in parallel, extract all requirements, and identify ambiguities. Clarifying questions were raised upfront (scoring formula edge cases, marker color scheme, Screen 3 granularity, caching strategy, ETL trigger mechanism) before any code was written.

**API and product direction:**
Open-Meteo was selected based on the criteria of being keyless, covering marine data (wave height) in the same ecosystem, and providing hourly resolution for 7 days — directly matching the sports-condition use case without any secondary API join.

**Data model and ETL design:**
The AI proposed the modular `src/` layout (fetcher → transformer → scorer), the two-parquet output model (`scores.parquet` + `best_slots.parquet`), and the linear-decay scoring formula. The user confirmed the exact scoring behavior (in-range = 1.0, linear decay to extreme, zero beyond extreme) after reviewing the proposed formula.

**Debugging and validation:**
- The AI caught a Plotly API deprecation (`titlefont` → `title=dict(font=dict(...))`) from live server logs.
- The PowerShell UTF-8 encoding corruption was detected and fixed using a Python repair script.
- Unit tests (`tests/test_scorer.py`) were written and executed to validate the scoring formula against boundary cases, NaN inputs, and extreme conditions.

**How AI output was reviewed and challenged:**
- The user corrected the SUP sport thresholds (wave and wind ranges were tightened based on domain knowledge).
- The user simplified the lower-bound scoring formula from a complex multi-condition branch to a simpler linear decay from zero.
- The user moved the unit selectors from the global sidebar to the Location Detail screen only (the AI's initial placement was reviewed and rejected as too broad).
- The user added the Bangkok-time hour picker on the Map Overview (not in the original spec — identified as a UX gap).

**Using AI to improve quality, not just generate code:**
The AI proactively: raised edge cases (marine API coverage gaps for near-land coordinates), suggested the 1-hour cache TTL to match the ETL staleness trigger, identified that `sys.exit(1)` in `etl.py` was being triggered by PowerShell stderr behavior rather than real ETL failures, and replaced all deprecated Streamlit `use_container_width=True` calls.

---

## ⚙️ Assumptions & Known Limitations

- **Marine API coverage**: Open-Meteo's Marine API returns HTTP 400 for coordinates too close to shore or on land. The ETL gracefully defaults `wave_height` to 0.0 for those locations and logs a warning.
- **Time zone**: All times are in Asia/Bangkok (UTC+7), as returned directly by Open-Meteo. All timestamp comparisons in the app are done without explicit tz-awareness to match the naive datetimes from the API.
- **Data window**: Filtered to 05:00–19:00 local time — nighttime conditions are excluded as out of scope for recreational water sports.
- **Forecast horizon**: 7 days (Open-Meteo free tier limit).
- **Wave model accuracy**: Open-Meteo uses ERA5 + GFS for wave forecasts; accuracy is lower for sheltered bays and enclosed coastlines.
- **Sport thresholds**: Optimal condition ranges and weights were defined by the candidate based on general water-sports knowledge. They are not sourced from authoritative meteorological standards.
- **Scoring formula lower bound**: For variables with a non-zero minimum (e.g., Surfing wave height min = 1 m), a value below the minimum decays linearly from 0 (at zero) to 1.0 (at min_range). This is a simplification — it does not model a separate lower-extreme threshold.

---

## 🌱 What I Would Improve with More Time

- Add historical data comparison (week-over-week and seasonal trends).
- Implement a tidal data layer using a tidal API for more precise surf condition scoring.
- Implement a wind direction data layer for more precise kitesurf condition scoring. 
- Add other global water-sports hubs (Bali, Canary Islands, Cape Town).
- Personelize optimal weather condition to better suit user level. 
