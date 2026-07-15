"""Direct unit tests for the pure helpers in plugins._base."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from email.utils import format_datetime

import pytest

from omni_weather_forecast_apis.plugins._base import (
    _forecast_has_content,
    _has_no_usable_content,
    as_float,
    build_alert,
    build_daily_point,
    build_hourly_point,
    build_minutely_point,
    build_source_forecast,
    cardinal_direction_to_degrees,
    fallback_condition,
    first_present,
    normalize_percent,
    normalize_severity,
    parse_retry_after,
    probability_from_fraction,
    probability_from_percent_value,
)
from omni_weather_forecast_apis.types import (
    AlertSeverity,
    ProviderId,
    WeatherCondition,
)


class TestAsFloat:
    def test_numbers_pass_through(self):
        assert as_float(3) == 3.0
        assert as_float(3.5) == 3.5
        assert as_float(-0.0) == 0.0

    def test_numeric_strings_convert(self):
        assert as_float("2.5") == 2.5
        assert as_float("-4") == -4.0

    def test_bool_is_rejected(self):
        booleans = [True, False]
        assert all(as_float(flag) is None for flag in booleans)

    def test_none_and_empty_string_are_rejected(self):
        assert as_float(None) is None
        assert as_float("") is None

    def test_garbage_is_rejected(self):
        assert as_float("n/a") is None
        assert as_float([1.0]) is None
        assert as_float({"value": 1.0}) is None


class TestParseRetryAfter:
    def test_delta_seconds(self):
        assert parse_retry_after("120") == 120.0
        assert parse_retry_after(" 0.5 ") == 0.5

    def test_negative_delta_clamps_to_zero(self):
        assert parse_retry_after("-30") == 0.0

    def test_http_date_in_future(self):
        future = datetime.now(tz=UTC) + timedelta(seconds=90)
        result = parse_retry_after(format_datetime(future, usegmt=True))
        assert result is not None
        assert 80 <= result <= 91

    def test_http_date_in_past_clamps_to_zero(self):
        past = datetime.now(tz=UTC) - timedelta(hours=1)
        assert parse_retry_after(format_datetime(past, usegmt=True)) == 0.0

    def test_none_empty_and_garbage(self):
        assert parse_retry_after(None) is None
        assert parse_retry_after("   ") is None
        assert parse_retry_after("soon") is None


class TestFirstPresent:
    def test_returns_first_non_null(self):
        assert first_present({"a": None, "b": 2, "c": 3}, "a", "b", "c") == 2

    def test_falsy_values_are_present(self):
        assert first_present({"a": 0}, "a") == 0
        assert first_present({"a": ""}, "a") == ""

    def test_all_missing_returns_none(self):
        assert first_present({"a": None}, "a", "b") is None


class TestProbabilityFromPercentValue:
    def test_percent_scale_is_downscaled(self):
        assert probability_from_percent_value(35) == 0.35
        assert probability_from_percent_value("80") == 0.8

    def test_one_percent_is_one_hundredth(self):
        # Regression: the old >1 heuristic read a raw 1 (1%) as 100%.
        assert probability_from_percent_value(1) == 0.01

    def test_clamping(self):
        assert probability_from_percent_value(150) == 1.0
        assert probability_from_percent_value(-5) == 0.0

    def test_non_numeric_returns_none(self):
        non_numeric = [None, "high", True]
        assert all(
            probability_from_percent_value(value) is None for value in non_numeric
        )


class TestProbabilityFromFraction:
    def test_fraction_passes_through(self):
        assert probability_from_fraction(0.35) == 0.35
        assert probability_from_fraction(1) == 1.0

    def test_clamping(self):
        assert probability_from_fraction(1.5) == 1.0
        assert probability_from_fraction(-0.5) == 0.0

    def test_non_numeric_returns_none(self):
        non_numeric = [None, "high", True]
        assert all(probability_from_fraction(value) is None for value in non_numeric)


class TestNormalizePercent:
    def test_fraction_is_upscaled(self):
        assert normalize_percent(0.5) == 50.0
        assert normalize_percent(1) == 100.0

    def test_percent_passes_through(self):
        assert normalize_percent(42) == 42.0

    def test_clamping(self):
        assert normalize_percent(250) == 100.0
        assert normalize_percent(-10) == 0.0

    def test_non_numeric_returns_none(self):
        assert normalize_percent("cloudy") is None


class TestNormalizeSeverity:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("Extreme", AlertSeverity.EXTREME),
            ("  severe ", AlertSeverity.SEVERE),
            ("MODERATE", AlertSeverity.MODERATE),
            ("minor", AlertSeverity.MINOR),
            ("advisory", AlertSeverity.UNKNOWN),
        ],
    )
    def test_mapping(self, text, expected):
        assert normalize_severity(text) is expected

    def test_none_returns_none(self):
        assert normalize_severity(None) is None


class TestCardinalDirection:
    @pytest.mark.parametrize(
        ("text", "degrees"),
        [("N", 0.0), ("ne", 45.0), (" SSW ", 202.5), ("nnw", 337.5)],
    )
    def test_known_directions(self, text, degrees):
        assert cardinal_direction_to_degrees(text) == degrees

    def test_unknown_and_none(self):
        assert cardinal_direction_to_degrees("NORTHISH") is None
        assert cardinal_direction_to_degrees(None) is None


class TestFallbackCondition:
    def test_code_mapping_wins(self):
        assert (
            fallback_condition(WeatherCondition.RAIN, "clear sky")
            is WeatherCondition.RAIN
        )

    def test_falls_back_to_text(self):
        assert fallback_condition(None, "heavy rain") is WeatherCondition.HEAVY_RAIN

    def test_no_signal_returns_none(self):
        assert fallback_condition(None, None) is None


class TestBuilders:
    def test_hourly_point_from_iso_string(self):
        point = build_hourly_point("2026-07-12T18:00:00+00:00", temperature=20.5)
        assert point.timestamp == datetime(2026, 7, 12, 18, tzinfo=UTC)
        assert point.timestamp_unix == int(point.timestamp.timestamp())
        assert point.temperature == 20.5

    def test_hourly_point_from_epoch(self):
        point = build_hourly_point(1_800_000_000)
        assert point.timestamp == datetime.fromtimestamp(1_800_000_000, tz=UTC)

    def test_hourly_point_rejects_unparseable(self):
        # Garbage strings surface the underlying isoformat ValueError;
        # non-coercible types hit the builder's own guard.
        with pytest.raises(ValueError, match="isoformat"):
            build_hourly_point("not a time")
        with pytest.raises(ValueError, match="parseable"):
            build_hourly_point(["2026-07-12"])

    def test_minutely_point(self):
        point = build_minutely_point(
            "2026-07-12T18:01:00Z",
            precipitation_intensity=0.4,
        )
        assert point.precipitation_intensity == 0.4
        with pytest.raises(ValueError, match="parseable"):
            build_minutely_point(None)

    def test_daily_point_from_date_string(self):
        point = build_daily_point("2026-07-12", temperature_max=30.0)
        assert point.date == date(2026, 7, 12)
        assert point.temperature_max == 30.0

    def test_daily_point_from_epoch(self):
        point = build_daily_point(1_800_000_000)
        assert point.date == datetime.fromtimestamp(1_800_000_000, tz=UTC).date()

    def test_daily_point_rejects_unparseable(self):
        with pytest.raises(ValueError, match=r"[Ii]soformat"):
            build_daily_point("someday")
        with pytest.raises(ValueError, match="parseable"):
            build_daily_point(("2026-07-12",))

    def test_daily_point_parses_astronomy(self):
        point = build_daily_point(
            "2026-07-12",
            sunrise="2026-07-12T05:45:00+00:00",
            sunset=1_800_000_000,
        )
        assert point.sunrise == datetime(2026, 7, 12, 5, 45, tzinfo=UTC)
        assert point.sunset == datetime.fromtimestamp(1_800_000_000, tz=UTC)

    def test_alert_requires_parseable_start(self):
        with pytest.raises(ValueError, match="isoformat"):
            build_alert(
                sender_name="NWS",
                event="Alert",
                start="whenever",
                end=None,
                description="",
            )

    def test_alert_normalizes_severity_and_optional_end(self):
        alert = build_alert(
            sender_name="NWS",
            event="Heat Advisory",
            start="2026-07-12T18:00:00Z",
            end=None,
            description="hot",
            severity="Severe",
        )
        assert alert.severity is AlertSeverity.SEVERE
        assert alert.end is None


class TestUsableContent:
    def _alert(self):
        return build_alert(
            sender_name="NWS",
            event="Heat Advisory",
            start="2026-07-12T18:00:00Z",
            end=None,
            description="hot",
        )

    def test_empty_forecasts_have_no_usable_content(self):
        empty = build_source_forecast(ProviderId.NWS)
        assert _forecast_has_content(empty) is False
        assert _has_no_usable_content([]) is True
        assert _has_no_usable_content([empty, empty]) is True

    def test_alerts_only_forecast_is_usable(self):
        alerts_only = build_source_forecast(ProviderId.NWS, alerts=[self._alert()])
        assert _forecast_has_content(alerts_only) is True
        assert _has_no_usable_content([alerts_only]) is False

    def test_any_data_section_makes_a_forecast_usable(self):
        hourly_only = build_source_forecast(
            ProviderId.NWS,
            hourly=[build_hourly_point("2026-07-12T18:00:00Z")],
        )
        empty = build_source_forecast(ProviderId.NWS)
        assert _has_no_usable_content([empty, hourly_only]) is False
