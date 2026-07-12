"""Direct tests for the condition-code and text mapping tables."""

from __future__ import annotations

import pytest

from omni_weather_forecast_apis.mapping import (
    OPENWEATHER_CONDITION_MAP,
    WMO_CODE_MAP,
    condition_from_text,
    map_met_norway_condition,
)
from omni_weather_forecast_apis.types import WeatherCondition


class TestOpenWeatherMap:
    def test_known_codes(self):
        assert OPENWEATHER_CONDITION_MAP[800] is WeatherCondition.CLEAR
        assert OPENWEATHER_CONDITION_MAP[511] is WeatherCondition.FREEZING_RAIN
        assert OPENWEATHER_CONDITION_MAP[781] is WeatherCondition.TORNADO

    def test_all_values_are_conditions(self):
        assert all(
            isinstance(value, WeatherCondition)
            for value in OPENWEATHER_CONDITION_MAP.values()
        )


class TestWMOMap:
    def test_known_codes(self):
        assert WMO_CODE_MAP[0] is WeatherCondition.CLEAR
        assert WMO_CODE_MAP[45] is WeatherCondition.FOG
        assert WMO_CODE_MAP[95] is WeatherCondition.THUNDERSTORM
        assert WMO_CODE_MAP[99] is WeatherCondition.THUNDERSTORM_HEAVY

    def test_all_values_are_conditions(self):
        assert all(
            isinstance(value, WeatherCondition) for value in WMO_CODE_MAP.values()
        )


class TestMetNorwayMapping:
    @pytest.mark.parametrize(
        ("symbol", "expected"),
        [
            ("clearsky_day", WeatherCondition.CLEAR),
            ("clearsky_night", WeatherCondition.CLEAR),
            ("partlycloudy_polartwilight", WeatherCondition.PARTLY_CLOUDY),
            ("heavyrainandthunder", WeatherCondition.THUNDERSTORM_HEAVY),
            ("lightsnowshowers_day", WeatherCondition.LIGHT_SNOW),
        ],
    )
    def test_suffix_stripping_and_mapping(self, symbol, expected):
        assert map_met_norway_condition(symbol) is expected

    def test_unknown_symbol(self):
        assert map_met_norway_condition("plasma_storm") is WeatherCondition.UNKNOWN


class TestConditionFromText:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("Tornado warning", WeatherCondition.TORNADO),
            ("Tropical Storm approaching", WeatherCondition.HURRICANE),
            ("Thunder and lightning", WeatherCondition.THUNDERSTORM),
            ("Freezing rain", WeatherCondition.FREEZING_RAIN),
            ("Light rain", WeatherCondition.LIGHT_RAIN),
            ("Patchy drizzle", WeatherCondition.DRIZZLE),
            ("Heavy rain at times", WeatherCondition.HEAVY_RAIN),
            ("Scattered showers", WeatherCondition.RAIN),
            ("Blizzard conditions", WeatherCondition.HEAVY_SNOW),
            ("Ice pellets", WeatherCondition.SLEET),
            ("Mist", WeatherCondition.HAZE),
            ("Mostly cloudy", WeatherCondition.MOSTLY_CLOUDY),
            ("Partly cloudy", WeatherCondition.PARTLY_CLOUDY),
            ("Sunny", WeatherCondition.CLEAR),
        ],
    )
    def test_keyword_matching(self, text, expected):
        assert condition_from_text(text) is expected

    def test_priority_thunder_beats_rain(self):
        # "Thunderstorm with rain" must map to a thunder condition, not RAIN.
        assert condition_from_text("Thunderstorm with rain") is (
            WeatherCondition.THUNDERSTORM
        )

    def test_case_and_whitespace_insensitive(self):
        assert condition_from_text("  HEAVY RAIN ") is WeatherCondition.HEAVY_RAIN

    def test_unrecognized_text_is_unknown(self):
        assert condition_from_text("vibes") is WeatherCondition.UNKNOWN

    def test_none_and_blank_return_none(self):
        assert condition_from_text(None) is None
        assert condition_from_text("   ") is None
