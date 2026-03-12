"""Tests for unit conversion utilities."""

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


class TestTemperatureConversions:
    def test_kelvin_to_celsius(self):
        assert celsius_from_kelvin(273.15) == pytest.approx(0.0)
        assert celsius_from_kelvin(373.15) == pytest.approx(100.0)

    def test_fahrenheit_to_celsius(self):
        assert celsius_from_fahrenheit(32.0) == pytest.approx(0.0)
        assert celsius_from_fahrenheit(212.0) == pytest.approx(100.0)


class TestWindSpeedConversions:
    def test_kmh_to_ms(self):
        assert ms_from_kmh(3.6) == pytest.approx(1.0)
        assert ms_from_kmh(36.0) == pytest.approx(10.0)

    def test_mph_to_ms(self):
        assert ms_from_mph(1.0) == pytest.approx(0.44704)

    def test_knots_to_ms(self):
        assert ms_from_knots(1.0) == pytest.approx(0.514444)


class TestPressureConversions:
    def test_inhg_to_hpa(self):
        assert hpa_from_inhg(29.92) == pytest.approx(1013.25, rel=1e-3)


class TestPrecipitationConversions:
    def test_inches_to_mm(self):
        assert mm_from_inches(1.0) == pytest.approx(25.4)

    def test_cm_to_mm(self):
        assert mm_from_cm(1.0) == pytest.approx(10.0)


class TestVisibilityConversions:
    def test_meters_to_km(self):
        assert km_from_meters(1000.0) == pytest.approx(1.0)

    def test_miles_to_km(self):
        assert km_from_miles(1.0) == pytest.approx(1.60934)


class TestProbabilityConversion:
    def test_percent_to_probability(self):
        assert probability_from_percent(50.0) == pytest.approx(0.5)
        assert probability_from_percent(100.0) == pytest.approx(1.0)
        assert probability_from_percent(0.0) == pytest.approx(0.0)


class TestSafeConvert:
    def test_with_value(self):
        assert safe_convert(273.15, celsius_from_kelvin) == pytest.approx(0.0)

    def test_with_none(self):
        assert safe_convert(None, celsius_from_kelvin) is None
