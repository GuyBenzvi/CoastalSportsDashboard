"""
app.py
------
Thailand Coastal Sports Dashboard — Streamlit application.

Three screens:
  1. Interactive Map    — Thailand coastline with sport-colored markers
  2. Location Detail   — 7-day hourly time-series + scoring per location
  3. Best Spots        — Best hour-slot per sport per day across all locations

Auto-triggers ETL if processed data is missing or stale (> 1 hour old).
"""

import json
import logging
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import folium
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from streamlit_folium import st_folium

from src.locations import LOCATIONS
from src.sports import (
    SPORTS,
    WIND_UNIT_FACTORS,
    WAVE_UNIT_FACTORS,
    get_grade,
)

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Thailand Coastal Sports Dashboard",
    page_icon="🌊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Paths ─────────────────────────────────────────────────────────────────────
PROCESSED_DIR  = Path("data") / "processed"
SCORES_PATH    = PROCESSED_DIR / "scores.parquet"
BEST_SLOTS_PATH= PROCESSED_DIR / "best_slots.parquet"
QR_PATH        = PROCESSED_DIR / "quality_report.json"
ETL_STALE_SECS = 3600  # 1 hour

logger = logging.getLogger(__name__)

# ── Styling ───────────────────────────────────────────────────────────────────
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
    }

    /* Dark sidebar */
    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #0f172a 0%, #1e293b 100%);
        color: #e2e8f0;
    }
    section[data-testid="stSidebar"] * { color: #e2e8f0 !important; }
    section[data-testid="stSidebar"] .stSelectbox label,
    section[data-testid="stSidebar"] .stRadio label { color: #94a3b8 !important; }

    /* Main background */
    .main { background: #0f172a; }
    .block-container { padding-top: 1.5rem; }

    /* Grade badge */
    .grade-badge {
        display: inline-block;
        padding: 4px 14px;
        border-radius: 999px;
        font-weight: 600;
        font-size: 0.85rem;
        letter-spacing: 0.05em;
    }

    /* Metric cards */
    .metric-card {
        background: rgba(30,41,59,0.85);
        border: 1px solid rgba(100,116,139,0.25);
        border-radius: 12px;
        padding: 16px 20px;
        text-align: center;
    }
    .metric-val  { font-size: 2rem; font-weight: 700; color: #f1f5f9; }
    .metric-label{ font-size: 0.78rem; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.08em; }

    /* Section titles */
    h1 { color: #f1f5f9 !important; }
    h2, h3 { color: #cbd5e1 !important; }

    /* Plotly chart background */
    .js-plotly-plot .plotly { background: transparent !important; }

    /* Best-slots table */
    .sport-header {
        font-size: 1.1rem;
        font-weight: 600;
        padding: 8px 0;
        border-bottom: 2px solid;
        margin-bottom: 8px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ─────────────────────────────────────────────────────────────────────────────
# Helper utilities
# ─────────────────────────────────────────────────────────────────────────────

def _data_is_stale() -> bool:
    """Return True if scores.parquet is missing or older than ETL_STALE_SECS."""
    if not SCORES_PATH.exists():
        return True
    age = time.time() - SCORES_PATH.stat().st_mtime
    return age > ETL_STALE_SECS


def _run_etl_if_needed(force: bool = False):
    """Auto-trigger ETL when data is missing or stale."""
    if not force and not _data_is_stale():
        return
    with st.spinner("⏳ Fetching fresh data from Open-Meteo APIs… (this may take ~30 s)"):
        result = subprocess.run(
            [sys.executable, "etl.py"] + (["--refresh"] if force else []),
            capture_output=True,
            text=True,
        )
    if result.returncode != 0:
        st.error(
            f"ETL encountered errors. Some data may be incomplete.\n\n"
            f"```\n{result.stderr[-2000:]}\n```"
        )
    else:
        st.success("✅ Data refreshed successfully!")
        st.rerun()


@st.cache_data(ttl=ETL_STALE_SECS)
def _load_scores() -> pd.DataFrame:
    if not SCORES_PATH.exists():
        return pd.DataFrame()
    return pd.read_parquet(SCORES_PATH)


@st.cache_data(ttl=ETL_STALE_SECS)
def _load_best_slots() -> pd.DataFrame:
    if not BEST_SLOTS_PATH.exists():
        return pd.DataFrame()
    return pd.read_parquet(BEST_SLOTS_PATH)


@st.cache_data(ttl=ETL_STALE_SECS)
def _load_quality_report() -> dict:
    if not QR_PATH.exists():
        return {}
    with open(QR_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _wind_label(unit: str) -> str:
    return f"Wind ({unit})"


def _wave_label(unit: str) -> str:
    return f"Wave Height ({unit})"


def _convert_wind(series: pd.Series, unit: str) -> pd.Series:
    return series * WIND_UNIT_FACTORS[unit]


def _convert_wave(series: pd.Series, unit: str) -> pd.Series:
    return series * WAVE_UNIT_FACTORS[unit]


def _sport_color(sport: str) -> str:
    return SPORTS.get(sport, {}).get("color", "#64748b")


def _grade_html(label: str, color: str) -> str:
    return (
        f'<span class="grade-badge" '
        f'style="background:{color}22;color:{color};border:1px solid {color}55;">'
        f'{label}</span>'
    )


# ─────────────────────────────────────────────────────────────────────────────
# Sidebar
# ─────────────────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("## 🌊 Thailand\nCoastal Sports")
    st.markdown("---")
    screen = st.radio(
        "Screen",
        ["🗺️ Map Overview", "📈 Location Detail", "🏆 Best Spots"],
        index=st.session_state.get("screen_idx", 0),
        key="screen_radio",
    )

    st.markdown("---")
    if st.button("🔄 Refresh Data", help="Force re-fetch from API"):
        _load_scores.clear()
        _load_best_slots.clear()
        _load_quality_report.clear()
        _run_etl_if_needed(force=True)

    # Quality report expander
    qr = _load_quality_report()
    if qr:
        with st.expander("📋 Data Quality Report"):
            run_at = qr.get("run_at", "—")
            st.caption(f"Last run: {run_at}")
            errors = qr.get("errors", [])
            if errors:
                st.error(f"{len(errors)} error(s) during ETL")
                for e in errors:
                    st.caption(f"• {e}")
            for loc_qc in qr.get("locations", []):
                issues = loc_qc.get("issues", [])
                if issues:
                    st.warning(f"**{loc_qc['slug']}**: {'; '.join(issues)}")


# ─────────────────────────────────────────────────────────────────────────────
# Auto-trigger ETL
# ─────────────────────────────────────────────────────────────────────────────
_run_etl_if_needed()

scores_df     = _load_scores()
best_slots_df = _load_best_slots()

if scores_df.empty:
    st.error("⚠️ No data available. Try clicking **Refresh Data** in the sidebar.")
    st.stop()

# Attach location metadata to scores if not already there
loc_lookup = {loc["slug"]: loc for loc in LOCATIONS}
if "name" not in scores_df.columns:
    scores_df["name"]   = scores_df["slug"].map(lambda s: loc_lookup.get(s, {}).get("name", s))
    scores_df["region"] = scores_df["slug"].map(lambda s: loc_lookup.get(s, {}).get("region", ""))
    scores_df["lat"]    = scores_df["slug"].map(lambda s: loc_lookup.get(s, {}).get("lat", 0))
    scores_df["lon"]    = scores_df["slug"].map(lambda s: loc_lookup.get(s, {}).get("lon", 0))

if "name" not in best_slots_df.columns and not best_slots_df.empty:
    best_slots_df["name"] = best_slots_df["slug"].map(
        lambda s: loc_lookup.get(s, {}).get("name", s)
    )


# ═════════════════════════════════════════════════════════════════════════════
# SCREEN 1 — Interactive Map
# ═════════════════════════════════════════════════════════════════════════════

if screen == "🗺️ Map Overview":
    st.markdown("# 🗺️ Thailand Coastal Sports Map")
    st.caption("Marker color = best water sport for that location. Click a marker to explore.")

    # ── Time selector (Bangkok time = UTC+7) ───────────────────────────────
    _now_bkk   = pd.Timestamp.utcnow() + pd.Timedelta(hours=7)
    _bkk_hour  = _now_bkk.hour
    _HOURS     = list(range(5, 20))          # 05:00 – 19:00
    _HOUR_OPTS = [f"{h:02d}:00" for h in _HOURS]

    # After 19:00 or before 05:00 → default to next day 09:00
    if _bkk_hour >= 19 or _bkk_hour < 5:
        _view_date    = (_now_bkk + pd.Timedelta(days=1)).date()
        _default_hour = 9
        _day_label    = "Tomorrow"
    else:
        _view_date    = _now_bkk.date()
        _default_hour = _bkk_hour
        _day_label    = "Today"

    _default_idx = _HOURS.index(_default_hour) if _default_hour in _HOURS else 4

    _col_info, _col_pick = st.columns([3, 1])
    with _col_info:
        st.markdown(
            f'<div style="color:#94a3b8;font-size:0.85rem;padding-top:6px;">'
            f'📅 Showing conditions for <b style="color:#f1f5f9;">'
            f'{_day_label} · {_view_date.strftime("%A, %d %b")}</b></div>',
            unsafe_allow_html=True,
        )
    with _col_pick:
        _sel_hour_str = st.selectbox(
            "⏰ Hour (Bangkok)", _HOUR_OPTS, index=_default_idx, key="map_hour",
            label_visibility="collapsed",
        )
    _sel_hour = int(_sel_hour_str.split(":")[0])

    # Filter scores to the selected date + hour
    _target_dt = pd.Timestamp(
        _view_date.year, _view_date.month, _view_date.day, _sel_hour
    )
    _hour_df = scores_df[scores_df["time"] == _target_dt]

    if not _hour_df.empty:
        location_summary = _hour_df.groupby("slug").first().reset_index()
    else:
        # Nearest available hour on the selected date (fallback)
        _date_df = scores_df[scores_df["time"].dt.date == _view_date]
        if _date_df.empty:
            _date_df = scores_df
        location_summary = (
            _date_df.assign(_dist=(_date_df["time"] - _target_dt).abs())
            .sort_values("_dist")
            .groupby("slug").first()
            .drop(columns=["_dist"])
            .reset_index()
        )

    # Build Folium map
    m = folium.Map(
        location=[9.0, 100.0],
        zoom_start=6,
        tiles="OpenStreetMap",
        width="100%",
    )

    # Sport legend
    legend_html = """
    <div style="position:fixed;bottom:30px;left:30px;z-index:9999;
                background:rgba(15,23,42,0.92);border:1px solid #334155;
                border-radius:10px;padding:12px 18px;font-family:Inter,sans-serif;">
        <div style="font-weight:600;color:#f1f5f9;margin-bottom:8px;font-size:13px;">Best Sport</div>
    """
    for sport, cfg in SPORTS.items():
        legend_html += (
            f'<div style="display:flex;align-items:center;gap:8px;margin:4px 0;">'
            f'<div style="width:14px;height:14px;border-radius:50%;background:{cfg["color"]};"></div>'
            f'<span style="color:#cbd5e1;font-size:12px;">{cfg["icon"]} {sport}</span></div>'
        )
    legend_html += "</div>"
    m.get_root().html.add_child(folium.Element(legend_html))

    for _, row in location_summary.iterrows():
        best_sport = row.get("best_sport", "SUP")
        color      = _sport_color(best_sport)
        score      = row.get("best_score", 0)
        grade, _   = get_grade(score)
        sport_icon = SPORTS.get(best_sport, {}).get("icon", "🌊")

        popup_html = f"""
        <div style="font-family:Inter,sans-serif;min-width:180px;">
            <b style="font-size:13px;color:#0f172a;">{row.get("name", row["slug"])}</b><br>
            <span style="color:#64748b;font-size:11px;">{row.get("region","")}</span><br><br>
            <span style="font-size:22px;">{sport_icon}</span>
            <span style="font-weight:600;color:{color};font-size:13px;margin-left:6px;">{best_sport}</span><br>
            <span style="font-size:12px;color:#374151;">Score: <b>{score:.0f}/100</b> — {grade}</span>
        </div>
        """

        folium.CircleMarker(
            location=[row["lat"], row["lon"]],
            radius=14,
            color=color,
            fill=True,
            fill_color=color,
            fill_opacity=0.85,
            weight=2.5,
            popup=folium.Popup(popup_html, max_width=240),
            tooltip=f"{row.get('name', row['slug'])} — {best_sport} ({score:.0f})",
        ).add_to(m)

    map_data = st_folium(m, width="100%", height=580, returned_objects=["last_object_clicked_popup"])

    # Sport score summary cards
    st.markdown("---")
    st.markdown("### 📊 Current Conditions Summary")
    cols = st.columns(len(SPORT_NAMES := list(SPORTS.keys())))
    for i, sport in enumerate(SPORT_NAMES):
        score_col = f"score_{sport}"
        if score_col in location_summary.columns:
            avg_score = location_summary[score_col].mean()
            best_loc  = location_summary.loc[location_summary[score_col].idxmax(), "name"]
            with cols[i]:
                color = _sport_color(sport)
                st.markdown(
                    f"""<div class="metric-card" style="border-top:3px solid {color};">
                        <div style="font-size:1.5rem;">{SPORTS[sport]['icon']}</div>
                        <div class="metric-val" style="color:{color};">{avg_score:.0f}</div>
                        <div class="metric-label">{sport} avg score</div>
                        <div style="font-size:0.72rem;color:#94a3b8;margin-top:6px;">
                            Best: {best_loc.split(" - ")[-1]}</div>
                    </div>""",
                    unsafe_allow_html=True,
                )


# ═════════════════════════════════════════════════════════════════════════════
# SCREEN 2 — Location Detail
# ═════════════════════════════════════════════════════════════════════════════

elif screen == "📈 Location Detail":
    st.markdown("# 📈 Location Weather & Scoring")

    # ── Unit selectors (only relevant here) ───────────────────────────────
    _uc1, _uc2, _uc3 = st.columns([2, 2, 4])
    with _uc1:
        wind_unit = st.selectbox(
            "💨 Wind unit", ["knots", "km/h", "m/s", "mph"], index=0, key="wind_unit"
        )
    with _uc2:
        wave_unit = st.selectbox(
            "🌊 Wave unit", ["meters", "feet"], index=0, key="wave_unit"
        )

    st.markdown("---")

    loc_names = [loc["name"] for loc in LOCATIONS]
    default_idx = 0
    if "selected_location" in st.session_state:
        try:
            default_idx = loc_names.index(st.session_state["selected_location"])
        except ValueError:
            pass

    selected_name = st.selectbox("Select Location", loc_names, index=default_idx)
    selected_slug = next(l["slug"] for l in LOCATIONS if l["name"] == selected_name)

    loc_df = scores_df[scores_df["slug"] == selected_slug].copy()

    if loc_df.empty:
        st.warning("No data available for this location.")
        st.stop()

    loc_df = loc_df.sort_values("time")

    # Current conditions header
    now_utc = pd.Timestamp.utcnow().tz_localize(None)
    future_rows = loc_df[loc_df["time"] >= now_utc]
    current = future_rows.iloc[0] if not future_rows.empty else loc_df.iloc[-1]

    best_sport = current.get("best_sport", "—")
    best_score = current.get("best_score", 0)
    grade_label, grade_color = get_grade(best_score)

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        wind_val = _convert_wind(pd.Series([current["wind_speed_ms"]]), wind_unit)[0]
        st.markdown(
            f'<div class="metric-card"><div class="metric-label">{_wind_label(wind_unit)}</div>'
            f'<div class="metric-val">{wind_val:.1f}</div></div>',
            unsafe_allow_html=True,
        )
    with col2:
        wave_val = _convert_wave(pd.Series([current["wave_height_m"]]), wave_unit)[0]
        st.markdown(
            f'<div class="metric-card"><div class="metric-label">{_wave_label(wave_unit)}</div>'
            f'<div class="metric-val">{wave_val:.2f}</div></div>',
            unsafe_allow_html=True,
        )
    with col3:
        st.markdown(
            f'<div class="metric-card"><div class="metric-label">Precipitation (mm)</div>'
            f'<div class="metric-val">{current["precipitation_mm"]:.1f}</div></div>',
            unsafe_allow_html=True,
        )
    with col4:
        sport_icon = SPORTS.get(best_sport, {}).get("icon", "🌊")
        sport_color = _sport_color(best_sport)
        st.markdown(
            f'<div class="metric-card"><div class="metric-label">Best Sport Now</div>'
            f'<div class="metric-val" style="font-size:1.4rem;color:{sport_color};">'
            f'{sport_icon} {best_sport}</div>'
            f'<div style="margin-top:4px;">{_grade_html(grade_label, grade_color)}</div></div>',
            unsafe_allow_html=True,
        )

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Time-series charts ────────────────────────────────────────────────
    plot_cfg = dict(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(15,23,42,0.6)",
        font=dict(color="#cbd5e1", family="Inter"),
        margin=dict(l=50, r=20, t=40, b=40),
        xaxis=dict(showgrid=False, color="#475569"),
        yaxis=dict(gridcolor="#1e293b", color="#475569"),
        legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(size=11)),
    )

    # Wind chart
    wind_converted = _convert_wind(loc_df["wind_speed_ms"], wind_unit)
    fig_wind = go.Figure()

    # Add optimal range bands for each sport
    for sport, cfg in SPORTS.items():
        v = cfg["variables"].get("wind_knots", {})
        lo = v.get("min_range", 0) * WIND_UNIT_FACTORS[wind_unit] / WIND_UNIT_FACTORS["knots"]
        hi = v.get("max_range", 0) * WIND_UNIT_FACTORS[wind_unit] / WIND_UNIT_FACTORS["knots"]
        fig_wind.add_hrect(
            y0=lo, y1=hi,
            fillcolor=cfg["color"], opacity=0.08,
            line_width=0,
            annotation_text=f'{sport} optimal',
            annotation_font_size=9,
            annotation_font_color=cfg["color"],
        )

    fig_wind.add_trace(go.Scatter(
        x=loc_df["time"], y=wind_converted,
        mode="lines", name=_wind_label(wind_unit),
        line=dict(color="#38bdf8", width=2),
        fill="tozeroy", fillcolor="rgba(56,189,248,0.08)",
    ))
    fig_wind.update_layout(title=f"💨 {_wind_label(wind_unit)}", height=260, **plot_cfg)
    st.plotly_chart(fig_wind, width='stretch')

    # Wave height chart
    wave_converted = _convert_wave(loc_df["wave_height_m"], wave_unit)
    fig_wave = go.Figure()

    for sport, cfg in SPORTS.items():
        v = cfg["variables"].get("wave_height_m", {})
        lo = v.get("min_range", 0) * WAVE_UNIT_FACTORS[wave_unit]
        hi = v.get("max_range", 0) * WAVE_UNIT_FACTORS[wave_unit]
        fig_wave.add_hrect(
            y0=lo, y1=hi,
            fillcolor=cfg["color"], opacity=0.08,
            line_width=0,
            annotation_text=f'{sport} optimal',
            annotation_font_size=9,
            annotation_font_color=cfg["color"],
        )

    fig_wave.add_trace(go.Scatter(
        x=loc_df["time"], y=wave_converted,
        mode="lines", name=_wave_label(wave_unit),
        line=dict(color="#818cf8", width=2),
        fill="tozeroy", fillcolor="rgba(129,140,248,0.08)",
    ))
    fig_wave.update_layout(title=f"🌊 {_wave_label(wave_unit)}", height=260, **plot_cfg)
    st.plotly_chart(fig_wave, width='stretch')

    # Precipitation chart
    fig_rain = go.Figure()
    fig_rain.add_trace(go.Bar(
        x=loc_df["time"], y=loc_df["precipitation_mm"],
        name="Precipitation (mm)",
        marker_color="#34d399",
        opacity=0.7,
    ))
    fig_rain.update_layout(title="🌧️ Precipitation (mm)", height=220, **plot_cfg)
    st.plotly_chart(fig_rain, width='stretch')

    # Sport scores time-series
    fig_scores = go.Figure()
    for sport, cfg in SPORTS.items():
        col = f"score_{sport}"
        if col in loc_df.columns:
            fig_scores.add_trace(go.Scatter(
                x=loc_df["time"], y=loc_df[col],
                mode="lines",
                name=f'{cfg["icon"]} {sport}',
                line=dict(color=cfg["color"], width=2.5),
            ))

    # Grade bands
    for lo, hi, label, color in [
        (76, 100, "Optimal", "#16A34A"),
        (51,  75, "Good",    "#84CC16"),
        (26,  50, "Caution", "#EAB308"),
        (0,   25, "Danger",  "#DC2626"),
    ]:
        fig_scores.add_hrect(
            y0=lo, y1=hi, fillcolor=color, opacity=0.05, line_width=0,
            annotation_text=label, annotation_position="left",
            annotation_font_size=9, annotation_font_color=color,
        )

    fig_scores.update_layout(
        title="🏅 Sport Scores (0–100)",
        height=300,
        yaxis=dict(range=[0, 105], gridcolor="#1e293b", color="#475569"),
        **{k: v for k, v in plot_cfg.items() if k != "yaxis"},
    )
    st.plotly_chart(fig_scores, width='stretch')


# ═════════════════════════════════════════════════════════════════════════════
# SCREEN 3 — Best Spots
# ═════════════════════════════════════════════════════════════════════════════

elif screen == "🏆 Best Spots":
    st.markdown("# 🏆 Best Spots & Times")
    st.caption("Best hour-slot per sport per location for each of the next 7 days.")

    if best_slots_df.empty:
        st.warning("No best-slots data available. Run ETL first.")
        st.stop()

    best_slots_df["best_time"] = pd.to_datetime(best_slots_df["best_time"])
    best_slots_df["date"]      = pd.to_datetime(best_slots_df["date"])

    # Filter to future dates only
    today = pd.Timestamp.today().normalize()
    future_slots = best_slots_df[best_slots_df["date"] >= today].copy()

    if future_slots.empty:
        st.info("No upcoming slots found — data may be from a past run. Refresh to update.")
        future_slots = best_slots_df.copy()

    sport_tabs = st.tabs(
        [f"{SPORTS[s]['icon']} {s}" for s in SPORTS.keys()]
    )

    for tab, sport in zip(sport_tabs, SPORTS.keys()):
        with tab:
            sport_df = future_slots[future_slots["sport"] == sport].copy()
            if sport_df.empty:
                st.info(f"No data for {sport}.")
                continue

            # Top daily ranking per location: best score for each day
            top_per_day = (
                sport_df.sort_values("score", ascending=False)
                .groupby("date")
                .head(3)
                .reset_index(drop=True)
            )

            color = SPORTS[sport]["color"]
            # Group by date
            for date_val, day_df in top_per_day.groupby("date", sort=True):
                date_str = pd.Timestamp(date_val).strftime("%A, %d %b")
                st.markdown(
                    f'<div class="sport-header" style="color:{color};border-color:{color}55;">'
                    f'📅 {date_str}</div>',
                    unsafe_allow_html=True,
                )
                for rank, (_, row) in enumerate(day_df.iterrows(), 1):
                    gl, gc = get_grade(row["score"])
                    time_str = pd.Timestamp(row["best_time"]).strftime("%H:%M")
                    medal = ["🥇", "🥈", "🥉"][rank - 1]
                    st.markdown(
                        f'{medal} **{row["name"]}** &nbsp;'
                        f'<span style="color:#64748b;font-size:0.85rem;">{row["region"]}</span> &nbsp;'
                        f'— &nbsp; ⏰ **{time_str}** &nbsp;'
                        f'— &nbsp; Score: <b style="color:{gc};">{row["score"]:.0f}/100</b> &nbsp;'
                        f'{_grade_html(gl, gc)}',
                        unsafe_allow_html=True,
                    )
                st.markdown("<br>", unsafe_allow_html=True)

            # Heatmap of scores across all locations and days
            st.markdown(f"#### 🗓️ Score Heatmap — {sport}")
            pivot = sport_df.pivot_table(
                index="name", columns="date", values="score", aggfunc="max"
            )
            pivot.columns = [pd.Timestamp(c).strftime("%d %b") for c in pivot.columns]

            fig_hm = go.Figure(data=go.Heatmap(
                z=pivot.values,
                x=pivot.columns.tolist(),
                y=pivot.index.tolist(),
                colorscale=[
                    [0.00, "#DC2626"],
                    [0.25, "#EAB308"],
                    [0.50, "#84CC16"],
                    [0.76, "#16A34A"],
                    [1.00, "#15803d"],
                ],
                zmin=0, zmax=100,
                text=np.round(pivot.values, 0),
                texttemplate="%{text:.0f}",
                hovertemplate="<b>%{y}</b><br>%{x}<br>Score: %{z:.0f}<extra></extra>",
                colorbar=dict(
                    title=dict(text="Score", font=dict(color="#cbd5e1")),
                    tickvals=[0, 25, 50, 75, 100],
                    ticktext=["0 Danger", "25", "50 Caution", "75", "100 Optimal"],
                    tickfont=dict(color="#cbd5e1"),
                ),
            ))
            fig_hm.update_layout(
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(15,23,42,0.6)",
                font=dict(color="#cbd5e1", family="Inter"),
                height=max(250, 50 + 40 * len(pivot)),
                margin=dict(l=20, r=20, t=20, b=40),
                xaxis=dict(side="top"),
            )
            st.plotly_chart(fig_hm, width='stretch')
