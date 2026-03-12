"""Tests for weather condition mappings."""

from omni_weather_forecast_apis.mapping.conditions import (
    OPENWEATHER_CONDITION_MAP,
    TOMORROW_IO_CONDITION_MAP,
    VISUAL_CROSSING_ICON_MAP,
    WEATHERAPI_CONDITION_MAP,
    WEATHERBIT_CONDITION_MAP,
    WMO_CODE_MAP,
    map_met_norway_condition,
    map_meteosource_condition,
    map_nws_condition,
    map_weather_unlocked_condition,
)
from omni_weather_forecast_apis.types.schema import WeatherCondition


class TestOpenWeatherMap:
    def test_clear(self):
        assert OPENWEATHER_CONDITION_MAP[800] == WeatherCondition.CLEAR

    def test_thunderstorm(self):
        assert OPENWEATHER_CONDITION_MAP[200] == WeatherCondition.THUNDERSTORM_RAIN

    def test_snow(self):
        assert OPENWEATHER_CONDITION_MAP[601] == WeatherCondition.SNOW


class TestWMOCodeMap:
    def test_clear(self):
        assert WMO_CODE_MAP[0] == WeatherCondition.CLEAR

    def test_fog(self):
        assert WMO_CODE_MAP[45] == WeatherCondition.FOG

    def test_heavy_rain(self):
        assert WMO_CODE_MAP[65] == WeatherCondition.HEAVY_RAIN


class TestTomorrowIOMap:
    def test_clear(self):
        assert TOMORROW_IO_CONDITION_MAP[1000] == WeatherCondition.CLEAR

    def test_rain(self):
        assert TOMORROW_IO_CONDITION_MAP[4001] == WeatherCondition.RAIN


class TestWeatherAPIMap:
    def test_clear(self):
        assert WEATHERAPI_CONDITION_MAP[1000] == WeatherCondition.CLEAR

    def test_fog(self):
        assert WEATHERAPI_CONDITION_MAP[1135] == WeatherCondition.FOG


class TestWeatherbitMap:
    def test_clear(self):
        assert WEATHERBIT_CONDITION_MAP[800] == WeatherCondition.CLEAR

    def test_overcast(self):
        assert WEATHERBIT_CONDITION_MAP[804] == WeatherCondition.OVERCAST


class TestVisualCrossingMap:
    def test_clear(self):
        assert VISUAL_CROSSING_ICON_MAP["clear-day"] == WeatherCondition.CLEAR

    def test_rain(self):
        assert VISUAL_CROSSING_ICON_MAP["rain"] == WeatherCondition.RAIN


class TestMETNorwayCondition:
    def test_clear_day(self):
        assert map_met_norway_condition("clearsky_day") == WeatherCondition.CLEAR

    def test_clear_night(self):
        assert map_met_norway_condition("clearsky_night") == WeatherCondition.CLEAR

    def test_rain(self):
        assert map_met_norway_condition("rain") == WeatherCondition.RAIN

    def test_unknown(self):
        assert map_met_norway_condition("nonexistent_day") == WeatherCondition.UNKNOWN


class TestNWSCondition:
    def test_clear(self):
        result = map_nws_condition(
            "https://api.weather.gov/icons/land/day/skc"
        )
        assert result == WeatherCondition.CLEAR

    def test_rain(self):
        result = map_nws_condition(
            "https://api.weather.gov/icons/land/day/rain"
        )
        assert result == WeatherCondition.RAIN

    def test_unknown(self):
        result = map_nws_condition("https://api.weather.gov/icons/land/day/unknown_code")
        assert result == WeatherCondition.UNKNOWN


class TestMeteosourceCondition:
    def test_clear(self):
        assert map_meteosource_condition(2) == WeatherCondition.CLEAR

    def test_unknown(self):
        assert map_meteosource_condition(999) == WeatherCondition.UNKNOWN


class TestWeatherUnlockedCondition:
    def test_clear(self):
        assert map_weather_unlocked_condition(0) == WeatherCondition.CLEAR

    def test_unknown(self):
        assert map_weather_unlocked_condition(999) == WeatherCondition.UNKNOWN
