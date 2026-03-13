from __future__ import annotations

from collections.abc import Callable


def celsius_from_kelvin(kelvin: float) -> float:
    return kelvin - 273.15


def celsius_from_fahrenheit(fahrenheit: float) -> float:
    return (fahrenheit - 32) * (5 / 9)


def ms_from_kmh(speed: float) -> float:
    return speed / 3.6


def ms_from_mph(speed: float) -> float:
    return speed * 0.44704


def ms_from_knots(speed: float) -> float:
    return speed * 0.514444


def hpa_from_inhg(pressure: float) -> float:
    return pressure * 33.8639


def mm_from_inches(amount: float) -> float:
    return amount * 25.4


def mm_from_cm(amount: float) -> float:
    return amount * 10.0


def km_from_meters(distance: float) -> float:
    return distance / 1000.0


def km_from_miles(distance: float) -> float:
    return distance * 1.60934


def probability_from_percent(value: float) -> float:
    return value / 100.0


def safe_convert(
    value: float | None,
    converter: Callable[[float], float],
) -> float | None:
    """Apply a conversion function when a value is present."""

    if value is None:
        return None
    return converter(value)
