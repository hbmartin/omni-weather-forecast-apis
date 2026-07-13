"""Direct tests for the unit conversion helpers."""

from __future__ import annotations

import pytest

from omni_weather_forecast_apis.mapping.units import (
    celsius_from_fahrenheit,
    celsius_from_kelvin,
    hpa_from_inhg,
    km_from_meters,
    km_from_miles,
    mm_from_cm,
    mm_from_inches,
    ms_from_kmh,
    ms_from_knots,
    ms_from_mph,
    probability_from_percent,
    safe_convert,
)


def test_temperature_conversions():
    assert celsius_from_kelvin(273.15) == 0.0
    assert celsius_from_kelvin(0) == -273.15
    assert celsius_from_fahrenheit(32) == 0.0
    assert celsius_from_fahrenheit(212) == pytest.approx(100.0)
    assert celsius_from_fahrenheit(-40) == pytest.approx(-40.0)


def test_speed_conversions():
    assert ms_from_kmh(36) == pytest.approx(10.0)
    assert ms_from_mph(1) == pytest.approx(0.44704)
    assert ms_from_knots(1) == pytest.approx(0.514444)


def test_pressure_and_precipitation_conversions():
    assert hpa_from_inhg(1) == pytest.approx(33.8639)
    assert mm_from_inches(1) == pytest.approx(25.4)
    assert mm_from_cm(2.3) == pytest.approx(23.0)


def test_distance_conversions():
    assert km_from_meters(1500) == pytest.approx(1.5)
    assert km_from_miles(1) == pytest.approx(1.60934)


def test_probability_from_percent():
    assert probability_from_percent(0) == 0.0
    assert probability_from_percent(100) == 1.0
    assert probability_from_percent(35) == pytest.approx(0.35)


def test_safe_convert():
    assert safe_convert(None, celsius_from_kelvin) is None
    assert safe_convert(273.15, celsius_from_kelvin) == 0.0
