"""Unit conversion functions. All return SI values per §3.1."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

# ─── Temperature → °C ───────────────────────────────────────────────


def celsius_from_kelvin(k: float) -> float:
    return k - 273.15


def celsius_from_fahrenheit(f: float) -> float:
    return (f - 32) * (5 / 9)


# ─── Wind Speed → m/s ───────────────────────────────────────────────


def ms_from_kmh(v: float) -> float:
    return v / 3.6


def ms_from_mph(v: float) -> float:
    return v * 0.44704


def ms_from_knots(v: float) -> float:
    return v * 0.514444


# ─── Pressure → hPa ─────────────────────────────────────────────────


def hpa_from_inhg(v: float) -> float:
    return v * 33.8639


# ─── Precipitation → mm ─────────────────────────────────────────────


def mm_from_inches(v: float) -> float:
    return v * 25.4


def mm_from_cm(v: float) -> float:
    return v * 10.0


# ─── Visibility → km ────────────────────────────────────────────────


def km_from_meters(v: float) -> float:
    return v / 1000.0


def km_from_miles(v: float) -> float:
    return v * 1.60934


# ─── Probability → 0–1 ──────────────────────────────────────────────


def probability_from_percent(v: float) -> float:
    return v / 100.0


# ─── Safe conversion helper ─────────────────────────────────────────


def safe_convert(
    value: float | None,
    converter: Callable[[float], float],
) -> float | None:
    """Apply a unit conversion, passing through None."""
    if value is None:
        return None
    return converter(value)
