"""Property-based tests for normalization and conversion helpers."""

from __future__ import annotations

import math

from hypothesis import given
from hypothesis import strategies as st

from omni_weather_forecast_apis.mapping import condition_from_text
from omni_weather_forecast_apis.mapping.units import (
    celsius_from_fahrenheit,
    km_from_miles,
    mm_from_inches,
    ms_from_kmh,
    ms_from_mph,
)
from omni_weather_forecast_apis.plugins._base import (
    as_float,
    cardinal_direction_to_degrees,
    normalize_percent,
    parse_retry_after,
    probability_from_fraction,
    probability_from_percent_value,
)
from omni_weather_forecast_apis.types import WeatherCondition

anything = st.one_of(
    st.none(),
    st.booleans(),
    st.integers(),
    st.floats(allow_nan=False),
    st.text(),
    st.lists(st.integers(), max_size=3),
    st.dictionaries(st.text(max_size=3), st.integers(), max_size=3),
)

finite_floats = st.floats(
    allow_nan=False,
    allow_infinity=False,
    min_value=-1e12,
    max_value=1e12,
)


@given(anything)
def test_as_float_never_raises_and_is_float_or_none(value):
    result = as_float(value)
    assert result is None or isinstance(result, float)


@given(anything)
def test_probability_from_percent_value_stays_in_unit_interval(value):
    result = probability_from_percent_value(value)
    assert result is None or 0.0 <= result <= 1.0


@given(anything)
def test_probability_from_fraction_stays_in_unit_interval(value):
    result = probability_from_fraction(value)
    assert result is None or 0.0 <= result <= 1.0


@given(anything)
def test_normalize_percent_stays_in_percent_range(value):
    result = normalize_percent(value)
    assert result is None or 0.0 <= result <= 100.0


@given(st.text())
def test_parse_retry_after_never_raises_and_never_negative(value):
    result = parse_retry_after(value)
    assert result is None or result >= 0.0


@given(st.text(max_size=20))
def test_cardinal_direction_in_compass_range(value):
    result = cardinal_direction_to_degrees(value)
    assert result is None or 0.0 <= result < 360.0


@given(st.one_of(st.none(), st.text(max_size=50)))
def test_condition_from_text_total_over_text(value):
    result = condition_from_text(value)
    assert result is None or isinstance(result, WeatherCondition)


@given(finite_floats)
def test_fahrenheit_round_trip(celsius):
    fahrenheit = celsius * 9 / 5 + 32
    assert math.isclose(
        celsius_from_fahrenheit(fahrenheit),
        celsius,
        rel_tol=1e-9,
        abs_tol=1e-6,
    )


@given(finite_floats, finite_floats)
def test_speed_conversions_are_monotonic(a, b):
    if a < b:
        assert ms_from_kmh(a) < ms_from_kmh(b)
        assert ms_from_mph(a) < ms_from_mph(b)


@given(st.floats(min_value=0, max_value=1e9, allow_nan=False))
def test_positive_amounts_stay_positive(value):
    assert mm_from_inches(value) >= 0
    assert km_from_miles(value) >= 0
