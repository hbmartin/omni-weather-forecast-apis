"""Weather condition code mappings for all providers."""

from omni_weather_forecast_apis.types.schema import WeatherCondition

# ─── OpenWeather condition ID → normalized condition ─────────────────
# Full list: https://openweathermap.org/weather-conditions

OPENWEATHER_CONDITION_MAP: dict[int, WeatherCondition] = {
    200: WeatherCondition.THUNDERSTORM_RAIN,
    201: WeatherCondition.THUNDERSTORM_RAIN,
    202: WeatherCondition.THUNDERSTORM_HEAVY,
    210: WeatherCondition.THUNDERSTORM,
    211: WeatherCondition.THUNDERSTORM,
    212: WeatherCondition.THUNDERSTORM_HEAVY,
    221: WeatherCondition.THUNDERSTORM,
    230: WeatherCondition.THUNDERSTORM_RAIN,
    231: WeatherCondition.THUNDERSTORM_RAIN,
    232: WeatherCondition.THUNDERSTORM_HEAVY,
    300: WeatherCondition.DRIZZLE,
    301: WeatherCondition.DRIZZLE,
    302: WeatherCondition.DRIZZLE,
    310: WeatherCondition.DRIZZLE,
    311: WeatherCondition.DRIZZLE,
    312: WeatherCondition.DRIZZLE,
    313: WeatherCondition.DRIZZLE,
    314: WeatherCondition.DRIZZLE,
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
    531: WeatherCondition.RAIN,
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
    771: WeatherCondition.UNKNOWN,
    781: WeatherCondition.TORNADO,
    800: WeatherCondition.CLEAR,
    801: WeatherCondition.MOSTLY_CLEAR,
    802: WeatherCondition.PARTLY_CLOUDY,
    803: WeatherCondition.MOSTLY_CLOUDY,
    804: WeatherCondition.OVERCAST,
}


# ─── WMO Weather interpretation codes ────────────────────────────────
# Used by Open-Meteo, Pirate Weather v2

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


# ─── Tomorrow.io weather codes ──────────────────────────────────────

TOMORROW_IO_CONDITION_MAP: dict[int, WeatherCondition] = {
    0: WeatherCondition.UNKNOWN,
    1000: WeatherCondition.CLEAR,
    1100: WeatherCondition.MOSTLY_CLEAR,
    1101: WeatherCondition.PARTLY_CLOUDY,
    1102: WeatherCondition.MOSTLY_CLOUDY,
    1001: WeatherCondition.OVERCAST,
    2000: WeatherCondition.FOG,
    2100: WeatherCondition.FOG,
    4000: WeatherCondition.DRIZZLE,
    4001: WeatherCondition.RAIN,
    4200: WeatherCondition.LIGHT_RAIN,
    4201: WeatherCondition.HEAVY_RAIN,
    5000: WeatherCondition.SNOW,
    5001: WeatherCondition.LIGHT_SNOW,
    5100: WeatherCondition.LIGHT_SNOW,
    5101: WeatherCondition.HEAVY_SNOW,
    6000: WeatherCondition.FREEZING_RAIN,
    6001: WeatherCondition.FREEZING_RAIN,
    6200: WeatherCondition.FREEZING_RAIN,
    6201: WeatherCondition.FREEZING_RAIN,
    7000: WeatherCondition.SLEET,
    7101: WeatherCondition.SLEET,
    7102: WeatherCondition.SLEET,
    8000: WeatherCondition.THUNDERSTORM,
}


# ─── WeatherAPI condition codes ──────────────────────────────────────

WEATHERAPI_CONDITION_MAP: dict[int, WeatherCondition] = {
    1000: WeatherCondition.CLEAR,
    1003: WeatherCondition.PARTLY_CLOUDY,
    1006: WeatherCondition.MOSTLY_CLOUDY,
    1009: WeatherCondition.OVERCAST,
    1030: WeatherCondition.HAZE,
    1063: WeatherCondition.LIGHT_RAIN,
    1066: WeatherCondition.LIGHT_SNOW,
    1069: WeatherCondition.SLEET,
    1072: WeatherCondition.FREEZING_RAIN,
    1087: WeatherCondition.THUNDERSTORM,
    1114: WeatherCondition.SNOW,
    1117: WeatherCondition.HEAVY_SNOW,
    1135: WeatherCondition.FOG,
    1147: WeatherCondition.FOG,
    1150: WeatherCondition.DRIZZLE,
    1153: WeatherCondition.DRIZZLE,
    1168: WeatherCondition.FREEZING_RAIN,
    1171: WeatherCondition.FREEZING_RAIN,
    1180: WeatherCondition.LIGHT_RAIN,
    1183: WeatherCondition.LIGHT_RAIN,
    1186: WeatherCondition.RAIN,
    1189: WeatherCondition.RAIN,
    1192: WeatherCondition.HEAVY_RAIN,
    1195: WeatherCondition.HEAVY_RAIN,
    1198: WeatherCondition.FREEZING_RAIN,
    1201: WeatherCondition.FREEZING_RAIN,
    1204: WeatherCondition.SLEET,
    1207: WeatherCondition.SLEET,
    1210: WeatherCondition.LIGHT_SNOW,
    1213: WeatherCondition.LIGHT_SNOW,
    1216: WeatherCondition.SNOW,
    1219: WeatherCondition.SNOW,
    1222: WeatherCondition.HEAVY_SNOW,
    1225: WeatherCondition.HEAVY_SNOW,
    1237: WeatherCondition.HAIL,
    1240: WeatherCondition.LIGHT_RAIN,
    1243: WeatherCondition.RAIN,
    1246: WeatherCondition.HEAVY_RAIN,
    1249: WeatherCondition.SLEET,
    1252: WeatherCondition.SLEET,
    1255: WeatherCondition.LIGHT_SNOW,
    1258: WeatherCondition.HEAVY_SNOW,
    1261: WeatherCondition.HAIL,
    1264: WeatherCondition.HAIL,
    1273: WeatherCondition.THUNDERSTORM_RAIN,
    1276: WeatherCondition.THUNDERSTORM_HEAVY,
    1279: WeatherCondition.THUNDERSTORM,
    1282: WeatherCondition.THUNDERSTORM_HEAVY,
}


# ─── Weatherbit condition codes ──────────────────────────────────────

WEATHERBIT_CONDITION_MAP: dict[int, WeatherCondition] = {
    200: WeatherCondition.THUNDERSTORM_RAIN,
    201: WeatherCondition.THUNDERSTORM_RAIN,
    202: WeatherCondition.THUNDERSTORM_HEAVY,
    230: WeatherCondition.THUNDERSTORM_RAIN,
    231: WeatherCondition.THUNDERSTORM_RAIN,
    232: WeatherCondition.THUNDERSTORM_HEAVY,
    233: WeatherCondition.THUNDERSTORM_HEAVY,
    300: WeatherCondition.DRIZZLE,
    301: WeatherCondition.DRIZZLE,
    302: WeatherCondition.DRIZZLE,
    500: WeatherCondition.LIGHT_RAIN,
    501: WeatherCondition.RAIN,
    502: WeatherCondition.HEAVY_RAIN,
    511: WeatherCondition.FREEZING_RAIN,
    520: WeatherCondition.LIGHT_RAIN,
    521: WeatherCondition.RAIN,
    522: WeatherCondition.HEAVY_RAIN,
    600: WeatherCondition.LIGHT_SNOW,
    601: WeatherCondition.SNOW,
    602: WeatherCondition.HEAVY_SNOW,
    610: WeatherCondition.SLEET,
    611: WeatherCondition.SLEET,
    612: WeatherCondition.SLEET,
    621: WeatherCondition.SNOW,
    622: WeatherCondition.HEAVY_SNOW,
    623: WeatherCondition.SNOW,
    700: WeatherCondition.HAZE,
    711: WeatherCondition.SMOKE,
    721: WeatherCondition.HAZE,
    731: WeatherCondition.DUST,
    741: WeatherCondition.FOG,
    751: WeatherCondition.FOG,
    800: WeatherCondition.CLEAR,
    801: WeatherCondition.MOSTLY_CLEAR,
    802: WeatherCondition.PARTLY_CLOUDY,
    803: WeatherCondition.MOSTLY_CLOUDY,
    804: WeatherCondition.OVERCAST,
    900: WeatherCondition.UNKNOWN,
}


# ─── Visual Crossing icon → condition ────────────────────────────────

VISUAL_CROSSING_ICON_MAP: dict[str, WeatherCondition] = {
    "clear-day": WeatherCondition.CLEAR,
    "clear-night": WeatherCondition.CLEAR,
    "partly-cloudy-day": WeatherCondition.PARTLY_CLOUDY,
    "partly-cloudy-night": WeatherCondition.PARTLY_CLOUDY,
    "cloudy": WeatherCondition.OVERCAST,
    "rain": WeatherCondition.RAIN,
    "showers-day": WeatherCondition.LIGHT_RAIN,
    "showers-night": WeatherCondition.LIGHT_RAIN,
    "snow": WeatherCondition.SNOW,
    "snow-showers-day": WeatherCondition.LIGHT_SNOW,
    "snow-showers-night": WeatherCondition.LIGHT_SNOW,
    "thunder": WeatherCondition.THUNDERSTORM,
    "thunder-rain": WeatherCondition.THUNDERSTORM_RAIN,
    "thunder-showers-day": WeatherCondition.THUNDERSTORM_RAIN,
    "thunder-showers-night": WeatherCondition.THUNDERSTORM_RAIN,
    "fog": WeatherCondition.FOG,
    "wind": WeatherCondition.UNKNOWN,
    "hail": WeatherCondition.HAIL,
    "sleet": WeatherCondition.SLEET,
}


# ─── MET Norway symbol codes ─────────────────────────────────────────


def map_met_norway_condition(symbol_code: str) -> WeatherCondition:
    """MET Norway symbol codes → normalized condition."""
    base = symbol_code
    for suffix in ("_day", "_night", "_polartwilight"):
        base = base.removesuffix(suffix)

    metno_map: dict[str, WeatherCondition] = {
        "clearsky": WeatherCondition.CLEAR,
        "fair": WeatherCondition.MOSTLY_CLEAR,
        "partlycloudy": WeatherCondition.PARTLY_CLOUDY,
        "cloudy": WeatherCondition.OVERCAST,
        "fog": WeatherCondition.FOG,
        "lightrainshowers": WeatherCondition.LIGHT_RAIN,
        "rainshowers": WeatherCondition.RAIN,
        "heavyrainshowers": WeatherCondition.HEAVY_RAIN,
        "lightrain": WeatherCondition.LIGHT_RAIN,
        "rain": WeatherCondition.RAIN,
        "heavyrain": WeatherCondition.HEAVY_RAIN,
        "lightrainshowersandthunder": WeatherCondition.THUNDERSTORM_RAIN,
        "rainshowersandthunder": WeatherCondition.THUNDERSTORM_RAIN,
        "heavyrainshowersandthunder": WeatherCondition.THUNDERSTORM_HEAVY,
        "lightrainandthunder": WeatherCondition.THUNDERSTORM_RAIN,
        "rainandthunder": WeatherCondition.THUNDERSTORM_RAIN,
        "heavyrainandthunder": WeatherCondition.THUNDERSTORM_HEAVY,
        "lightsnowshowers": WeatherCondition.LIGHT_SNOW,
        "snowshowers": WeatherCondition.SNOW,
        "heavysnowshowers": WeatherCondition.HEAVY_SNOW,
        "lightsnow": WeatherCondition.LIGHT_SNOW,
        "snow": WeatherCondition.SNOW,
        "heavysnow": WeatherCondition.HEAVY_SNOW,
        "lightsnowandthunder": WeatherCondition.THUNDERSTORM,
        "snowandthunder": WeatherCondition.THUNDERSTORM,
        "heavysnowandthunder": WeatherCondition.THUNDERSTORM_HEAVY,
        "lightsleet": WeatherCondition.SLEET,
        "sleet": WeatherCondition.SLEET,
        "heavysleet": WeatherCondition.SLEET,
        "lightsleetshowers": WeatherCondition.SLEET,
        "sleetshowers": WeatherCondition.SLEET,
        "heavysleetshowers": WeatherCondition.SLEET,
        "lightsleetandthunder": WeatherCondition.THUNDERSTORM_RAIN,
        "sleetandthunder": WeatherCondition.THUNDERSTORM_RAIN,
        "heavysleetandthunder": WeatherCondition.THUNDERSTORM_HEAVY,
        "lightsleetshowersandthunder": WeatherCondition.THUNDERSTORM_RAIN,
        "sleetshowersandthunder": WeatherCondition.THUNDERSTORM_RAIN,
        "heavysleetshowersandthunder": WeatherCondition.THUNDERSTORM_HEAVY,
        "lightssnowshowersandthunder": WeatherCondition.THUNDERSTORM,
        "snowshowersandthunder": WeatherCondition.THUNDERSTORM,
        "heavysnowshowersandthunder": WeatherCondition.THUNDERSTORM_HEAVY,
    }

    return metno_map.get(base, WeatherCondition.UNKNOWN)


# ─── NWS icon/forecast text mapping ──────────────────────────────────


def map_nws_condition(icon_url: str) -> WeatherCondition:
    """Map NWS icon URL to normalized condition.

    NWS icons follow patterns like:
    https://api.weather.gov/icons/land/day/skc
    """
    icon_code = icon_url.rstrip("/").split("/")[-1].split(",")[0].split("?")[0]

    nws_map: dict[str, WeatherCondition] = {
        "skc": WeatherCondition.CLEAR,
        "few": WeatherCondition.MOSTLY_CLEAR,
        "sct": WeatherCondition.PARTLY_CLOUDY,
        "bkn": WeatherCondition.MOSTLY_CLOUDY,
        "ovc": WeatherCondition.OVERCAST,
        "wind_skc": WeatherCondition.CLEAR,
        "wind_few": WeatherCondition.MOSTLY_CLEAR,
        "wind_sct": WeatherCondition.PARTLY_CLOUDY,
        "wind_bkn": WeatherCondition.MOSTLY_CLOUDY,
        "wind_ovc": WeatherCondition.OVERCAST,
        "snow": WeatherCondition.SNOW,
        "rain_snow": WeatherCondition.SLEET,
        "rain_sleet": WeatherCondition.SLEET,
        "snow_sleet": WeatherCondition.SLEET,
        "fzra": WeatherCondition.FREEZING_RAIN,
        "rain_fzra": WeatherCondition.FREEZING_RAIN,
        "snow_fzra": WeatherCondition.FREEZING_RAIN,
        "sleet": WeatherCondition.SLEET,
        "rain": WeatherCondition.RAIN,
        "rain_showers": WeatherCondition.RAIN,
        "rain_showers_hi": WeatherCondition.LIGHT_RAIN,
        "tsra": WeatherCondition.THUNDERSTORM_RAIN,
        "tsra_sct": WeatherCondition.THUNDERSTORM_RAIN,
        "tsra_hi": WeatherCondition.THUNDERSTORM,
        "tornado": WeatherCondition.TORNADO,
        "hurricane": WeatherCondition.HURRICANE,
        "tropical_storm": WeatherCondition.HURRICANE,
        "dust": WeatherCondition.DUST,
        "smoke": WeatherCondition.SMOKE,
        "haze": WeatherCondition.HAZE,
        "hot": WeatherCondition.CLEAR,
        "cold": WeatherCondition.CLEAR,
        "blizzard": WeatherCondition.HEAVY_SNOW,
        "fog": WeatherCondition.FOG,
    }

    return nws_map.get(icon_code, WeatherCondition.UNKNOWN)


# ─── Stormglass ──────────────────────────────────────────────────────


def map_stormglass_condition(_data: dict[str, object]) -> WeatherCondition:
    """Stormglass doesn't provide condition codes; return UNKNOWN."""
    return WeatherCondition.UNKNOWN


# ─── Meteosource ─────────────────────────────────────────────────────

_METEOSOURCE_MAP: dict[int, WeatherCondition] = {
    1: WeatherCondition.UNKNOWN,
    2: WeatherCondition.CLEAR,
    3: WeatherCondition.MOSTLY_CLEAR,
    4: WeatherCondition.PARTLY_CLOUDY,
    5: WeatherCondition.MOSTLY_CLOUDY,
    6: WeatherCondition.OVERCAST,
    7: WeatherCondition.FOG,
    8: WeatherCondition.LIGHT_RAIN,
    9: WeatherCondition.RAIN,
    10: WeatherCondition.HEAVY_RAIN,
    11: WeatherCondition.LIGHT_SNOW,
    12: WeatherCondition.SNOW,
    13: WeatherCondition.HEAVY_SNOW,
    14: WeatherCondition.LIGHT_RAIN,
    15: WeatherCondition.RAIN,
    16: WeatherCondition.HEAVY_RAIN,
    17: WeatherCondition.LIGHT_SNOW,
    18: WeatherCondition.SNOW,
    19: WeatherCondition.HEAVY_SNOW,
    20: WeatherCondition.SLEET,
    21: WeatherCondition.SLEET,
    22: WeatherCondition.SLEET,
    23: WeatherCondition.THUNDERSTORM,
    24: WeatherCondition.THUNDERSTORM_RAIN,
    25: WeatherCondition.THUNDERSTORM_HEAVY,
    26: WeatherCondition.HAIL,
    27: WeatherCondition.DRIZZLE,
    28: WeatherCondition.FREEZING_RAIN,
    29: WeatherCondition.FREEZING_RAIN,
    30: WeatherCondition.DUST,
}


def map_meteosource_condition(icon_id: int) -> WeatherCondition:
    """Map Meteosource icon_id to normalized condition."""
    return _METEOSOURCE_MAP.get(icon_id, WeatherCondition.UNKNOWN)


# ─── Weather Unlocked ────────────────────────────────────────────────


def map_weather_unlocked_condition(weather_type_id: int) -> WeatherCondition:
    """Map Weather Unlocked wx_code to normalized condition."""
    wu_map: dict[int, WeatherCondition] = {
        0: WeatherCondition.CLEAR,
        1: WeatherCondition.MOSTLY_CLEAR,
        2: WeatherCondition.PARTLY_CLOUDY,
        3: WeatherCondition.OVERCAST,
        10: WeatherCondition.HAZE,
        21: WeatherCondition.LIGHT_RAIN,
        22: WeatherCondition.RAIN,
        23: WeatherCondition.HEAVY_RAIN,
        24: WeatherCondition.FREEZING_RAIN,
        29: WeatherCondition.THUNDERSTORM_RAIN,
        38: WeatherCondition.LIGHT_SNOW,
        39: WeatherCondition.SNOW,
        40: WeatherCondition.HEAVY_SNOW,
        45: WeatherCondition.HAIL,
        49: WeatherCondition.FOG,
        50: WeatherCondition.DRIZZLE,
    }
    return wu_map.get(weather_type_id, WeatherCondition.UNKNOWN)
