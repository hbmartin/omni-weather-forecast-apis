"""Tests for Weatherbit condition mapping."""

from omni_weather_forecast_apis.plugins.weatherbit import _map_condition
from omni_weather_forecast_apis.types import WeatherCondition


def test_code_233_maps_to_hail() -> None:
    assert _map_condition("Thunderstorm with hail", 233) == WeatherCondition.HAIL
