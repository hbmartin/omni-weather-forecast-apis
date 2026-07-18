"""Direct tests for the condition-code and text mapping tables."""

from __future__ import annotations

import pytest

from omni_weather_forecast_apis.mapping import (
    MET_OFFICE_CONDITION_MAP,
    OPENWEATHER_CONDITION_MAP,
    WEATHERKIT_CONDITION_MAP,
    WMO_CODE_MAP,
    XWEATHER_CLOUDS_CODED_MAP,
    XWEATHER_WEATHER_CODED_MAP,
    condition_from_text,
    map_met_norway_condition,
    map_met_office_condition,
    map_xweather_coded,
    met_office_is_day,
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

    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            # Regression: the generic "showers" keyword used to win over
            # every wintry phrase, turning all of these into RAIN.
            ("Snow Showers", WeatherCondition.SNOW),
            ("Light snow showers", WeatherCondition.LIGHT_SNOW),
            ("Chance Snow Showers", WeatherCondition.SNOW),
            ("Sleet showers", WeatherCondition.SLEET),
            ("Wintry Showers", WeatherCondition.SLEET),
            ("Rain And Snow Showers", WeatherCondition.SLEET),
            ("Freezing drizzle", WeatherCondition.FREEZING_RAIN),
            # Regression: NWS-style sunny variants used to collapse to CLEAR.
            ("Mostly Sunny", WeatherCondition.MOSTLY_CLEAR),
            ("Partly Sunny", WeatherCondition.PARTLY_CLOUDY),
            # Regression: Visual Crossing "Partially cloudy" and bare
            # "Cloudy" used to fall through to UNKNOWN.
            ("Partially cloudy", WeatherCondition.PARTLY_CLOUDY),
            ("Cloudy", WeatherCondition.MOSTLY_CLOUDY),
        ],
    )
    def test_wintry_showers_and_sunny_variants(self, text, expected):
        assert condition_from_text(text) is expected

    def test_case_and_whitespace_insensitive(self):
        assert condition_from_text("  HEAVY RAIN ") is WeatherCondition.HEAVY_RAIN

    def test_unrecognized_text_is_unknown(self):
        assert condition_from_text("vibes") is WeatherCondition.UNKNOWN

    def test_none_and_blank_return_none(self):
        assert condition_from_text(None) is None
        assert condition_from_text("   ") is None


class TestMetOfficeMap:
    def test_known_codes(self):
        assert map_met_office_condition(1) is WeatherCondition.CLEAR
        assert map_met_office_condition(5) is WeatherCondition.HAZE
        assert map_met_office_condition(15) is WeatherCondition.HEAVY_RAIN
        assert map_met_office_condition(18) is WeatherCondition.SLEET
        assert map_met_office_condition(30) is WeatherCondition.THUNDERSTORM
        assert map_met_office_condition(-1) is WeatherCondition.DRIZZLE

    def test_unknown_code_maps_to_unknown(self):
        assert map_met_office_condition(4) is WeatherCondition.UNKNOWN
        assert map_met_office_condition(99) is WeatherCondition.UNKNOWN

    def test_is_day_variants(self):
        assert met_office_is_day(1) is True
        assert met_office_is_day(0) is False
        assert met_office_is_day(10) is True
        assert met_office_is_day(9) is False
        assert met_office_is_day(7) is None

    def test_all_values_are_conditions(self):
        assert all(
            isinstance(value, WeatherCondition)
            for value in MET_OFFICE_CONDITION_MAP.values()
        )


class TestXweatherCoded:
    @pytest.mark.parametrize(
        ("coded", "clouds", "expected"),
        [
            ("::R", None, WeatherCondition.RAIN),
            (":L:R", None, WeatherCondition.LIGHT_RAIN),
            (":VH:R", None, WeatherCondition.HEAVY_RAIN),
            (":L:S", None, WeatherCondition.LIGHT_SNOW),
            (":H:T", None, WeatherCondition.THUNDERSTORM_HEAVY),
            ("::ZR", None, WeatherCondition.FREEZING_RAIN),
            (":L:F", None, WeatherCondition.FOG),
            ("::", "OV", WeatherCondition.OVERCAST),
            (None, "CL", WeatherCondition.CLEAR),
            (None, "FW", WeatherCondition.MOSTLY_CLEAR),
            ("::", "BK", WeatherCondition.MOSTLY_CLOUDY),
        ],
    )
    def test_coded_combinations(self, coded, clouds, expected):
        assert map_xweather_coded(coded, clouds) is expected

    def test_unknown_inputs_return_none(self):
        assert map_xweather_coded(None, None) is None
        assert map_xweather_coded("not-coded", None) is None
        assert map_xweather_coded("::", "??") is None

    def test_all_values_are_conditions(self):
        tables = (XWEATHER_WEATHER_CODED_MAP, XWEATHER_CLOUDS_CODED_MAP)
        assert all(
            isinstance(value, WeatherCondition)
            for table in tables
            for value in table.values()
        )


class TestWeatherKitMap:
    def test_known_codes(self):
        assert WEATHERKIT_CONDITION_MAP["Clear"] is WeatherCondition.CLEAR
        assert WEATHERKIT_CONDITION_MAP["Cloudy"] is WeatherCondition.OVERCAST
        assert (
            WEATHERKIT_CONDITION_MAP["Thunderstorms"] is WeatherCondition.THUNDERSTORM
        )
        assert WEATHERKIT_CONDITION_MAP["WintryMix"] is WeatherCondition.SLEET
        assert WEATHERKIT_CONDITION_MAP["Blizzard"] is WeatherCondition.HEAVY_SNOW
        assert WEATHERKIT_CONDITION_MAP["TropicalStorm"] is WeatherCondition.HURRICANE

    def test_all_values_are_conditions(self):
        assert all(
            isinstance(value, WeatherCondition)
            for value in WEATHERKIT_CONDITION_MAP.values()
        )
