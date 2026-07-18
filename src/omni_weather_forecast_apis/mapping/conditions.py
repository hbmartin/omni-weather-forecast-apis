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
    "lightrainshowersandthunder": WeatherCondition.THUNDERSTORM_RAIN,
    "rainshowersandthunder": WeatherCondition.THUNDERSTORM_RAIN,
    "heavyrainshowersandthunder": WeatherCondition.THUNDERSTORM_HEAVY,
    "lightsleetshowers": WeatherCondition.SLEET,
    "sleetshowers": WeatherCondition.SLEET,
    "heavysleetshowers": WeatherCondition.SLEET,
    "lightsleetshowersandthunder": WeatherCondition.THUNDERSTORM_RAIN,
    "sleetshowersandthunder": WeatherCondition.THUNDERSTORM_RAIN,
    "heavysleetshowersandthunder": WeatherCondition.THUNDERSTORM_HEAVY,
    "lightsnowshowers": WeatherCondition.LIGHT_SNOW,
    "snowshowers": WeatherCondition.SNOW,
    "heavysnowshowers": WeatherCondition.HEAVY_SNOW,
    "lightsnowshowersandthunder": WeatherCondition.THUNDERSTORM_RAIN,
    "snowshowersandthunder": WeatherCondition.THUNDERSTORM_RAIN,
    "heavysnowshowersandthunder": WeatherCondition.THUNDERSTORM_HEAVY,
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


MET_OFFICE_CONDITION_MAP: dict[int, WeatherCondition] = {
    -1: WeatherCondition.DRIZZLE,  # trace rain
    0: WeatherCondition.CLEAR,  # clear night
    1: WeatherCondition.CLEAR,  # sunny day
    2: WeatherCondition.PARTLY_CLOUDY,  # partly cloudy night
    3: WeatherCondition.PARTLY_CLOUDY,  # partly cloudy day
    5: WeatherCondition.HAZE,  # mist
    6: WeatherCondition.FOG,
    7: WeatherCondition.MOSTLY_CLOUDY,  # cloudy
    8: WeatherCondition.OVERCAST,
    9: WeatherCondition.LIGHT_RAIN,  # light rain shower night
    10: WeatherCondition.LIGHT_RAIN,  # light rain shower day
    11: WeatherCondition.DRIZZLE,
    12: WeatherCondition.LIGHT_RAIN,
    13: WeatherCondition.HEAVY_RAIN,  # heavy rain shower night
    14: WeatherCondition.HEAVY_RAIN,  # heavy rain shower day
    15: WeatherCondition.HEAVY_RAIN,
    16: WeatherCondition.SLEET,  # sleet shower night
    17: WeatherCondition.SLEET,  # sleet shower day
    18: WeatherCondition.SLEET,
    19: WeatherCondition.HAIL,  # hail shower night
    20: WeatherCondition.HAIL,  # hail shower day
    21: WeatherCondition.HAIL,
    22: WeatherCondition.LIGHT_SNOW,  # light snow shower night
    23: WeatherCondition.LIGHT_SNOW,  # light snow shower day
    24: WeatherCondition.LIGHT_SNOW,
    25: WeatherCondition.HEAVY_SNOW,  # heavy snow shower night
    26: WeatherCondition.HEAVY_SNOW,  # heavy snow shower day
    27: WeatherCondition.HEAVY_SNOW,
    28: WeatherCondition.THUNDERSTORM_RAIN,  # thunder shower night
    29: WeatherCondition.THUNDERSTORM_RAIN,  # thunder shower day
    30: WeatherCondition.THUNDERSTORM,
}

_MET_OFFICE_NIGHT_CODES: frozenset[int] = frozenset({0, 2, 9, 13, 16, 19, 22, 25, 28})
_MET_OFFICE_DAY_CODES: frozenset[int] = frozenset({1, 3, 10, 14, 17, 20, 23, 26, 29})


def map_met_office_condition(code: int) -> WeatherCondition:
    """Normalize Met Office significant weather codes."""

    return MET_OFFICE_CONDITION_MAP.get(code, WeatherCondition.UNKNOWN)


def met_office_is_day(code: int) -> bool | None:
    """Infer day/night from codes that carry a day or night variant."""

    if code in _MET_OFFICE_DAY_CODES:
        return True
    if code in _MET_OFFICE_NIGHT_CODES:
        return False
    return None


XWEATHER_WEATHER_CODED_MAP: dict[str, WeatherCondition] = {
    "A": WeatherCondition.HAIL,
    "BD": WeatherCondition.DUST,
    "BN": WeatherCondition.SAND,
    "BR": WeatherCondition.HAZE,  # mist
    "BS": WeatherCondition.SNOW,  # blowing snow
    "F": WeatherCondition.FOG,
    "H": WeatherCondition.HAZE,
    "IC": WeatherCondition.SNOW,  # ice crystals
    "IF": WeatherCondition.FOG,  # ice fog
    "IP": WeatherCondition.SLEET,  # ice pellets
    "K": WeatherCondition.SMOKE,
    "L": WeatherCondition.DRIZZLE,
    "R": WeatherCondition.RAIN,
    "RS": WeatherCondition.SLEET,  # rain/snow mix
    "RW": WeatherCondition.RAIN,  # rain showers
    "S": WeatherCondition.SNOW,
    "SI": WeatherCondition.SLEET,  # snow/ice-pellet mix
    "SW": WeatherCondition.SNOW,  # snow showers
    "T": WeatherCondition.THUNDERSTORM,
    "TO": WeatherCondition.TORNADO,
    "UP": WeatherCondition.UNKNOWN,
    "VA": WeatherCondition.DUST,  # volcanic ash
    "WM": WeatherCondition.SLEET,  # wintry mix
    "WP": WeatherCondition.TORNADO,  # waterspouts
    "ZF": WeatherCondition.FOG,  # freezing fog
    "ZL": WeatherCondition.FREEZING_RAIN,  # freezing drizzle
    "ZR": WeatherCondition.FREEZING_RAIN,
    "ZY": WeatherCondition.FREEZING_RAIN,  # freezing spray
}

XWEATHER_CLOUDS_CODED_MAP: dict[str, WeatherCondition] = {
    "CL": WeatherCondition.CLEAR,
    "FW": WeatherCondition.MOSTLY_CLEAR,  # fair / mostly sunny
    "SC": WeatherCondition.PARTLY_CLOUDY,  # scattered clouds
    "BK": WeatherCondition.MOSTLY_CLOUDY,  # broken clouds
    "OV": WeatherCondition.OVERCAST,
}

_XWEATHER_LIGHT_INTENSITIES: frozenset[str] = frozenset({"VL", "L"})
_XWEATHER_HEAVY_INTENSITIES: frozenset[str] = frozenset({"H", "VH"})

_XWEATHER_INTENSITY_VARIANTS: dict[
    WeatherCondition, tuple[WeatherCondition, WeatherCondition]
] = {
    WeatherCondition.RAIN: (WeatherCondition.LIGHT_RAIN, WeatherCondition.HEAVY_RAIN),
    WeatherCondition.SNOW: (WeatherCondition.LIGHT_SNOW, WeatherCondition.HEAVY_SNOW),
    WeatherCondition.THUNDERSTORM: (
        WeatherCondition.THUNDERSTORM,
        WeatherCondition.THUNDERSTORM_HEAVY,
    ),
}


def _apply_xweather_intensity(
    condition: WeatherCondition,
    intensity: str,
) -> WeatherCondition:
    variants = _XWEATHER_INTENSITY_VARIANTS.get(condition)
    if variants is None:
        return condition
    light, heavy = variants
    if intensity in _XWEATHER_LIGHT_INTENSITIES:
        return light
    if intensity in _XWEATHER_HEAVY_INTENSITIES:
        return heavy
    return condition


def map_xweather_coded(
    coded: str | None,
    clouds_coded: str | None,
) -> WeatherCondition | None:
    """Normalize an Xweather ``coverage:intensity:weather`` code.

    Falls back to the cloud-cover code when no weather phenomenon is coded.
    """

    if coded and len(parts := coded.split(":")) == 3:
        _, intensity, weather = parts
        if weather and (mapped := XWEATHER_WEATHER_CODED_MAP.get(weather)):
            return _apply_xweather_intensity(mapped, intensity)
    if clouds_coded:
        return XWEATHER_CLOUDS_CODED_MAP.get(clouds_coded)
    return None


WEATHERKIT_CONDITION_MAP: dict[str, WeatherCondition] = {
    "Clear": WeatherCondition.CLEAR,
    "MostlyClear": WeatherCondition.MOSTLY_CLEAR,
    "PartlyCloudy": WeatherCondition.PARTLY_CLOUDY,
    "MostlyCloudy": WeatherCondition.MOSTLY_CLOUDY,
    "Cloudy": WeatherCondition.OVERCAST,
    "Foggy": WeatherCondition.FOG,
    "Haze": WeatherCondition.HAZE,
    "Smoky": WeatherCondition.SMOKE,
    "Dust": WeatherCondition.DUST,
    "Drizzle": WeatherCondition.DRIZZLE,
    "FreezingDrizzle": WeatherCondition.FREEZING_RAIN,
    "FreezingRain": WeatherCondition.FREEZING_RAIN,
    "SunShowers": WeatherCondition.LIGHT_RAIN,
    "Rain": WeatherCondition.RAIN,
    "HeavyRain": WeatherCondition.HEAVY_RAIN,
    "Flurries": WeatherCondition.LIGHT_SNOW,
    "SunFlurries": WeatherCondition.LIGHT_SNOW,
    "Snow": WeatherCondition.SNOW,
    "BlowingSnow": WeatherCondition.SNOW,
    "HeavySnow": WeatherCondition.HEAVY_SNOW,
    "Blizzard": WeatherCondition.HEAVY_SNOW,
    "Sleet": WeatherCondition.SLEET,
    "WintryMix": WeatherCondition.SLEET,
    "MixedRainAndSleet": WeatherCondition.SLEET,
    "MixedRainAndSnow": WeatherCondition.SLEET,
    "MixedRainfall": WeatherCondition.SLEET,
    "MixedSnowAndSleet": WeatherCondition.SLEET,
    "Hail": WeatherCondition.HAIL,
    "Thunderstorms": WeatherCondition.THUNDERSTORM,
    "ScatteredThunderstorms": WeatherCondition.THUNDERSTORM,
    "IsolatedThunderstorms": WeatherCondition.THUNDERSTORM,
    "SevereThunderstorm": WeatherCondition.THUNDERSTORM_HEAVY,
    "StrongStorms": WeatherCondition.THUNDERSTORM_HEAVY,
    "Hurricane": WeatherCondition.HURRICANE,
    "TropicalStorm": WeatherCondition.HURRICANE,
    "Tornado": WeatherCondition.TORNADO,
}


def condition_from_text(text: str | None) -> WeatherCondition | None:
    """Infer a normalized condition from provider summary text."""

    if text is None:
        return None

    normalized = text.strip().lower()
    if not normalized:
        return None

    # Ordered most-specific first: wintry phrases must win before the generic
    # "showers"/"rain" keywords, and "partly/mostly sunny" before bare "sunny".
    keyword_map: tuple[tuple[tuple[str, ...], WeatherCondition], ...] = (
        (("tornado",), WeatherCondition.TORNADO),
        (("hurricane", "tropical storm"), WeatherCondition.HURRICANE),
        (("thunder", "lightning"), WeatherCondition.THUNDERSTORM),
        (("freezing rain", "freezing drizzle"), WeatherCondition.FREEZING_RAIN),
        (("sleet", "ice pellets", "rain and snow", "wintry"), WeatherCondition.SLEET),
        (("hail",), WeatherCondition.HAIL),
        (("light snow",), WeatherCondition.LIGHT_SNOW),
        (("heavy snow", "blizzard"), WeatherCondition.HEAVY_SNOW),
        (("snow",), WeatherCondition.SNOW),
        (("drizzle",), WeatherCondition.DRIZZLE),
        (("light rain",), WeatherCondition.LIGHT_RAIN),
        (("heavy rain", "downpour"), WeatherCondition.HEAVY_RAIN),
        (("rain shower", "showers"), WeatherCondition.RAIN),
        (("rain",), WeatherCondition.RAIN),
        (("fog",), WeatherCondition.FOG),
        (("smoke",), WeatherCondition.SMOKE),
        (("dust",), WeatherCondition.DUST),
        (("sand",), WeatherCondition.SAND),
        (("haze", "mist"), WeatherCondition.HAZE),
        (("overcast",), WeatherCondition.OVERCAST),
        (("mostly cloudy",), WeatherCondition.MOSTLY_CLOUDY),
        (
            ("partly cloudy", "partly cloud", "partially cloud"),
            WeatherCondition.PARTLY_CLOUDY,
        ),
        (("cloudy",), WeatherCondition.MOSTLY_CLOUDY),
        (("mostly clear", "mostly sunny"), WeatherCondition.MOSTLY_CLEAR),
        (("partly sunny",), WeatherCondition.PARTLY_CLOUDY),
        (("clear", "sunny"), WeatherCondition.CLEAR),
    )
    for keywords, condition in keyword_map:
        if any(keyword in normalized for keyword in keywords):
            return condition
    return WeatherCondition.UNKNOWN
