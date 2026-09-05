"""
tests/test_scorer.py
--------------------
Unit tests for the sport scoring logic.
"""

import pytest
import pandas as pd
from src.scorer import _component_score, score_sport


class TestComponentScore:
    """Tests for the core scoring function."""

    def test_in_range_returns_1(self):
        # Wind 12–30 knots optimal for Kitesurf
        assert _component_score(20, 12, 30, 40) == 1.0

    def test_at_lower_boundary_returns_1(self):
        assert _component_score(12, 12, 30, 40) == 1.0

    def test_at_upper_boundary_returns_1(self):
        assert _component_score(30, 12, 30, 40) == 1.0

    def test_at_extreme_returns_0(self):
        assert _component_score(40, 12, 30, 40) == 0.0

    def test_beyond_extreme_returns_0(self):
        assert _component_score(50, 12, 30, 40) == 0.0

    def test_midpoint_between_boundary_and_extreme_returns_half(self):
        # Between 30 (max_range) and 40 (extreme), midpoint = 35
        # Linear decay: 1.0 at 30 → 0.0 at 40, so 35 → 0.5
        result = _component_score(35, 12, 30, 40)
        assert abs(result - 0.5) < 1e-9

    def test_nan_returns_0(self):
        import math
        assert _component_score(float("nan"), 12, 30, 40) == 0.0


class TestSportScoring:
    """Integration tests for full sport scoring."""

    def _make_df(self, wind_knots, wave_m, precip_mm):
        return pd.DataFrame({
            "wind_knots":        [wind_knots],
            "wave_height_m":     [wave_m],
            "precipitation_mm":  [precip_mm],
            "wind_speed_ms":     [wind_knots / 1.94384],
        })

    def test_kitesurf_optimal_conditions_scores_100(self):
        df = self._make_df(wind_knots=20, wave_m=0.5, precip_mm=5)
        score = score_sport(df, "Kitesurf").iloc[0]
        assert score == pytest.approx(100.0, abs=0.1)

    def test_kitesurf_no_wind_below_extreme_scores_less_than_100(self):
        df = self._make_df(wind_knots=0, wave_m=0.5, precip_mm=5)
        score = score_sport(df, "Kitesurf").iloc[0]
        assert score < 100.0

    def test_surfing_optimal_big_wave(self):
        df = self._make_df(wind_knots=10, wave_m=2.0, precip_mm=3)
        score = score_sport(df, "Surfing").iloc[0]
        assert score == pytest.approx(100.0, abs=0.1)

    def test_sup_calm_conditions_scores_high(self):
        df = self._make_df(wind_knots=5, wave_m=0.2, precip_mm=0)
        score = score_sport(df, "SUP").iloc[0]
        assert score == pytest.approx(100.0, abs=0.1)

    def test_extreme_wind_kitesurf_scores_0(self):
        df = self._make_df(wind_knots=45, wave_m=0.5, precip_mm=5)
        score = score_sport(df, "Kitesurf").iloc[0]
        # Wind is beyond extreme (40 knots) → wind component = 0 → total ≤ 30
        assert score < 31.0
