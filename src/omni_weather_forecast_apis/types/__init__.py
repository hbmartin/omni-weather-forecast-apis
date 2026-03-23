from importlib import import_module
from typing import TYPE_CHECKING, Any

from omni_weather_forecast_apis.types.config import (
    OmniWeatherConfig,
    ProviderRegistration,
    RateLimitConfig,
)
from omni_weather_forecast_apis.types.plugin import (
    PluginCapabilities,
    PluginFetchError,
    PluginFetchParams,
    PluginFetchResult,
    PluginFetchSuccess,
    PluginInstance,
    ProviderConfigModel,
    WeatherPlugin,
)
from omni_weather_forecast_apis.types.schema import (
    AlertSeverity,
    DailyDataPoint,
    ErrorCode,
    ForecastRequest,
    ForecastResponse,
    ForecastResponseRequest,
    ForecastResponseSummary,
    Granularity,
    LogHook,
    MinutelyDataPoint,
    ModelSource,
    ProviderError,
    ProviderErrorDetail,
    ProviderId,
    ProviderLogEvent,
    ProviderResult,
    ProviderSuccess,
    SourceForecast,
    WeatherAlert,
    WeatherCondition,
    WeatherDataPoint,
)

if TYPE_CHECKING:
    from omni_weather_forecast_apis.plugins.google_weather import GoogleWeatherConfig
    from omni_weather_forecast_apis.plugins.met_norway import METNorwayConfig
    from omni_weather_forecast_apis.plugins.meteosource import MeteosourceConfig
    from omni_weather_forecast_apis.plugins.nws import NWSConfig, NWSGridOverride
    from omni_weather_forecast_apis.plugins.open_meteo import OpenMeteoConfig
    from omni_weather_forecast_apis.plugins.openweather import OpenWeatherConfig
    from omni_weather_forecast_apis.plugins.pirate_weather import PirateWeatherConfig
    from omni_weather_forecast_apis.plugins.stormglass import StormglassConfig
    from omni_weather_forecast_apis.plugins.tomorrow_io import TomorrowIOConfig
    from omni_weather_forecast_apis.plugins.visual_crossing import VisualCrossingConfig
    from omni_weather_forecast_apis.plugins.weather_unlocked import (
        WeatherUnlockedConfig,
    )
    from omni_weather_forecast_apis.plugins.weatherapi import WeatherAPIConfig
    from omni_weather_forecast_apis.plugins.weatherbit import WeatherbitConfig

_PROVIDER_CONFIG_EXPORTS = {
    "GoogleWeatherConfig": (
        "omni_weather_forecast_apis.plugins.google_weather",
        "GoogleWeatherConfig",
    ),
    "METNorwayConfig": (
        "omni_weather_forecast_apis.plugins.met_norway",
        "METNorwayConfig",
    ),
    "MeteosourceConfig": (
        "omni_weather_forecast_apis.plugins.meteosource",
        "MeteosourceConfig",
    ),
    "NWSConfig": ("omni_weather_forecast_apis.plugins.nws", "NWSConfig"),
    "NWSGridOverride": (
        "omni_weather_forecast_apis.plugins.nws",
        "NWSGridOverride",
    ),
    "OpenMeteoConfig": (
        "omni_weather_forecast_apis.plugins.open_meteo",
        "OpenMeteoConfig",
    ),
    "OpenWeatherConfig": (
        "omni_weather_forecast_apis.plugins.openweather",
        "OpenWeatherConfig",
    ),
    "PirateWeatherConfig": (
        "omni_weather_forecast_apis.plugins.pirate_weather",
        "PirateWeatherConfig",
    ),
    "StormglassConfig": (
        "omni_weather_forecast_apis.plugins.stormglass",
        "StormglassConfig",
    ),
    "TomorrowIOConfig": (
        "omni_weather_forecast_apis.plugins.tomorrow_io",
        "TomorrowIOConfig",
    ),
    "VisualCrossingConfig": (
        "omni_weather_forecast_apis.plugins.visual_crossing",
        "VisualCrossingConfig",
    ),
    "WeatherAPIConfig": (
        "omni_weather_forecast_apis.plugins.weatherapi",
        "WeatherAPIConfig",
    ),
    "WeatherbitConfig": (
        "omni_weather_forecast_apis.plugins.weatherbit",
        "WeatherbitConfig",
    ),
    "WeatherUnlockedConfig": (
        "omni_weather_forecast_apis.plugins.weather_unlocked",
        "WeatherUnlockedConfig",
    ),
}


def __getattr__(name: str) -> Any:
    if name not in _PROVIDER_CONFIG_EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    module_name, export_name = _PROVIDER_CONFIG_EXPORTS[name]
    value = getattr(import_module(module_name), export_name)
    globals()[name] = value
    return value

__all__ = [
    "AlertSeverity",
    "DailyDataPoint",
    "ErrorCode",
    "ForecastRequest",
    "ForecastResponse",
    "ForecastResponseRequest",
    "ForecastResponseSummary",
    "GoogleWeatherConfig",
    "Granularity",
    "LogHook",
    "METNorwayConfig",
    "MeteosourceConfig",
    "MinutelyDataPoint",
    "ModelSource",
    "NWSConfig",
    "NWSGridOverride",
    "OmniWeatherConfig",
    "OpenMeteoConfig",
    "OpenWeatherConfig",
    "PirateWeatherConfig",
    "PluginCapabilities",
    "PluginFetchError",
    "PluginFetchParams",
    "PluginFetchResult",
    "PluginFetchSuccess",
    "PluginInstance",
    "ProviderConfigModel",
    "ProviderError",
    "ProviderErrorDetail",
    "ProviderId",
    "ProviderLogEvent",
    "ProviderRegistration",
    "ProviderResult",
    "ProviderSuccess",
    "RateLimitConfig",
    "SourceForecast",
    "StormglassConfig",
    "TomorrowIOConfig",
    "VisualCrossingConfig",
    "WeatherAPIConfig",
    "WeatherAlert",
    "WeatherCondition",
    "WeatherDataPoint",
    "WeatherPlugin",
    "WeatherUnlockedConfig",
    "WeatherbitConfig",
]
