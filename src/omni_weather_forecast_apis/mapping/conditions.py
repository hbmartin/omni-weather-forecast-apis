from __future__ import annotations

from omni_weather_forecast_apis.types.schema import WeatherCondition

OPENWEATHER_CONDITION_MAP: dict[int, WeatherCondition] = {
    200: WeatherCondition.THUNDERSTORM_RAIN,
    201: WeatherCondition.THUNDERSTORM_RAIN,
    202: WeatherCondition.THUNDERSTORM_HEAVY,
    210: WeatherCondition.THUNDERSTORM,
    211: WeatherCondition.THUNDERSTORM,
    212: WeatherCondition.THUNDERSTORM_HEAVY,
    221: WeatherCondition.THUNDERSTORM_HEAVY,
    230: WeatherCondition.THUNDERSTORM_RAIN,
    231: WeatherCondition.THUNDERSTORM_RAIN,
    232: WeatherCondition.THUNDERSTORM_HEAVY,
    300: WeatherCondition.DRIZZLE,
    301: WeatherCondition.DRIZZLE,
    302: WeatherCondition.DRIZZLE,
    310: WeatherCondition.DRIZZLE,
    311: WeatherCondition.DRIZZLE,
    312: WeatherCondition.DRIZZLE,
    313: WeatherCondition.RAIN,
    314: WeatherCondition.HEAVY_RAIN,
    321: WeatherCondition.DRIZZLE,
    500: WeatherCondition.LIGHT_RAIN,
    501: WeatherCondition.RAIN,
    502: WeatherCondition.HEAVY_RAIN,
    503: WeatherCondition.HEAVY_RAIN,
    504: WeatherCondition.HEAVY_RAIN,
    511: WeatherCondition.FREEZING_RAIN,
    520: WeatherCondition.LIGHT_RAIN,
    521: WeatherCondition.RAIN,
    522: WeatherCondition.HEAVY_RAIN,
    531: WeatherCondition.HEAVY_RAIN,
    600: WeatherCondition.LIGHT_SNOW,
    601: WeatherCondition.SNOW,
    602: WeatherCondition.HEAVY_SNOW,
    611: WeatherCondition.SLEET,
    612: WeatherCondition.SLEET,
    613: WeatherCondition.SLEET,
    615: WeatherCondition.SLEET,
    616: WeatherCondition.SLEET,
    620: WeatherCondition.LIGHT_SNOW,
    621: WeatherCondition.SNOW,
    622: WeatherCondition.HEAVY_SNOW,
    701: WeatherCondition.HAZE,
    711: WeatherCondition.SMOKE,
    721: WeatherCondition.HAZE,
    731: WeatherCondition.DUST,
    741: WeatherCondition.FOG,
    751: WeatherCondition.SAND,
    761: WeatherCondition.DUST,
    762: WeatherCondition.DUST,
    771: WeatherCondition.HAZE,
    781: WeatherCondition.TORNADO,
    800: WeatherCondition.CLEAR,
    801: WeatherCondition.MOSTLY_CLEAR,
    802: WeatherCondition.PARTLY_CLOUDY,
    803: WeatherCondition.MOSTLY_CLOUDY,
    804: WeatherCondition.OVERCAST,
}

WMO_CODE_MAP: dict[int, WeatherCondition] = {
    0: WeatherCondition.CLEAR,
    1: WeatherCondition.MOSTLY_CLEAR,
    2: WeatherCondition.PARTLY_CLOUDY,
    3: WeatherCondition.OVERCAST,
    45: WeatherCondition.FOG,
    48: WeatherCondition.FOG,
    51: WeatherCondition.DRIZZLE,
    53: WeatherCondition.DRIZZLE,
    55: WeatherCondition.DRIZZLE,
    56: WeatherCondition.FREEZING_RAIN,
    57: WeatherCondition.FREEZING_RAIN,
    61: WeatherCondition.LIGHT_RAIN,
    63: WeatherCondition.RAIN,
    65: WeatherCondition.HEAVY_RAIN,
    66: WeatherCondition.FREEZING_RAIN,
    67: WeatherCondition.FREEZING_RAIN,
    71: WeatherCondition.LIGHT_SNOW,
    73: WeatherCondition.SNOW,
    75: WeatherCondition.HEAVY_SNOW,
    77: WeatherCondition.SNOW,
    80: WeatherCondition.LIGHT_RAIN,
    81: WeatherCondition.RAIN,
    82: WeatherCondition.HEAVY_RAIN,
    85: WeatherCondition.LIGHT_SNOW,
    86: WeatherCondition.HEAVY_SNOW,
    95: WeatherCondition.THUNDERSTORM,
    96: WeatherCondition.THUNDERSTORM_RAIN,
    99: WeatherCondition.THUNDERSTORM_HEAVY,
}

MET_NORWAY_CONDITION_MAP: dict[str, WeatherCondition] = {
    "clearsky": WeatherCondition.CLEAR,
    "fair": WeatherCondition.MOSTLY_CLEAR,
    "partlycloudy": WeatherCondition.PARTLY_CLOUDY,
    "cloudy": WeatherCondition.OVERCAST,
    "fog": WeatherCondition.FOG,
    "lightrainshowers": WeatherCondition.LIGHT_RAIN,
    "rainshowers": WeatherCondition.RAIN,
    "heavyrainshowers": WeatherCondition.HEAVY_RAIN,
    "lightsleetshowers": WeatherCondition.SLEET,
    "sleetshowers": WeatherCondition.SLEET,
    "heavysleetshowers": WeatherCondition.SLEET,
    "lightsnowshowers": WeatherCondition.LIGHT_SNOW,
    "snowshowers": WeatherCondition.SNOW,
    "heavysnowshowers": WeatherCondition.HEAVY_SNOW,
    "lightrain": WeatherCondition.LIGHT_RAIN,
    "rain": WeatherCondition.RAIN,
    "heavyrain": WeatherCondition.HEAVY_RAIN,
    "lightsleet": WeatherCondition.SLEET,
    "sleet": WeatherCondition.SLEET,
    "heavysleet": WeatherCondition.SLEET,
    "lightsnow": WeatherCondition.LIGHT_SNOW,
    "snow": WeatherCondition.SNOW,
    "heavysnow": WeatherCondition.HEAVY_SNOW,
    "lightrainandthunder": WeatherCondition.THUNDERSTORM_RAIN,
    "rainandthunder": WeatherCondition.THUNDERSTORM_RAIN,
    "heavyrainandthunder": WeatherCondition.THUNDERSTORM_HEAVY,
    "lightsleetandthunder": WeatherCondition.THUNDERSTORM_RAIN,
    "sleetandthunder": WeatherCondition.THUNDERSTORM_RAIN,
    "heavysleetandthunder": WeatherCondition.THUNDERSTORM_HEAVY,
    "lightsnowandthunder": WeatherCondition.THUNDERSTORM_RAIN,
    "snowandthunder": WeatherCondition.THUNDERSTORM_RAIN,
    "heavysnowandthunder": WeatherCondition.THUNDERSTORM_HEAVY,
}


def map_met_norway_condition(symbol_code: str) -> WeatherCondition:
    """Normalize MET Norway symbol codes."""

    base = symbol_code
    for suffix in ("_day", "_night", "_polartwilight"):
        base = base.removesuffix(suffix)
    return MET_NORWAY_CONDITION_MAP.get(base, WeatherCondition.UNKNOWN)


def condition_from_text(text: str | None) -> WeatherCondition | None:
    """Infer a normalized condition from provider summary text."""

    if text is None:
        return None

    normalized = text.strip().lower()
    if not normalized:
        return None

    keyword_map: tuple[tuple[tuple[str, ...], WeatherCondition], ...] = (
        (("tornado",), WeatherCondition.TORNADO),
        (("hurricane", "tropical storm"), WeatherCondition.HURRICANE),
        (("thunder", "lightning"), WeatherCondition.THUNDERSTORM),
        (("freezing rain",), WeatherCondition.FREEZING_RAIN),
        (("drizzle",), WeatherCondition.DRIZZLE),
        (("heavy rain", "downpour"), WeatherCondition.HEAVY_RAIN),
        (("rain shower", "showers"), WeatherCondition.RAIN),
        (("rain",), WeatherCondition.RAIN),
        (("hail",), WeatherCondition.HAIL),
        (("heavy snow", "blizzard"), WeatherCondition.HEAVY_SNOW),
        (("snow shower",), WeatherCondition.SNOW),
        (("snow",), WeatherCondition.SNOW),
        (("sleet", "ice pellets"), WeatherCondition.SLEET),
        (("fog",), WeatherCondition.FOG),
        (("smoke",), WeatherCondition.SMOKE),
        (("dust",), WeatherCondition.DUST),
        (("sand",), WeatherCondition.SAND),
        (("haze", "mist"), WeatherCondition.HAZE),
        (("overcast",), WeatherCondition.OVERCAST),
        (("mostly cloudy",), WeatherCondition.MOSTLY_CLOUDY),
        (("partly cloudy", "partly cloud"), WeatherCondition.PARTLY_CLOUDY),
        (("mostly clear",), WeatherCondition.MOSTLY_CLEAR),
        (("clear", "sunny"), WeatherCondition.CLEAR),
    )
    for keywords, condition in keyword_map:
        if any(keyword in normalized for keyword in keywords):
            return condition
    return WeatherCondition.UNKNOWN
