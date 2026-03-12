"""Plugin registry for all weather providers."""

from typing import TYPE_CHECKING

from omni_weather_forecast_apis.plugins.google_weather import google_weather_plugin
from omni_weather_forecast_apis.plugins.met_norway import met_norway_plugin
from omni_weather_forecast_apis.plugins.meteosource import meteosource_plugin
from omni_weather_forecast_apis.plugins.nws import nws_plugin
from omni_weather_forecast_apis.plugins.open_meteo import open_meteo_plugin
from omni_weather_forecast_apis.plugins.openweather import openweather_plugin
from omni_weather_forecast_apis.plugins.pirate_weather import pirate_weather_plugin
from omni_weather_forecast_apis.plugins.stormglass import stormglass_plugin
from omni_weather_forecast_apis.plugins.tomorrow_io import tomorrow_io_plugin
from omni_weather_forecast_apis.plugins.visual_crossing import visual_crossing_plugin
from omni_weather_forecast_apis.plugins.weather_unlocked import weather_unlocked_plugin
from omni_weather_forecast_apis.plugins.weatherapi import weatherapi_plugin
from omni_weather_forecast_apis.plugins.weatherbit import weatherbit_plugin
from omni_weather_forecast_apis.types.schema import ProviderId

if TYPE_CHECKING:
    from omni_weather_forecast_apis.types.plugin import WeatherPlugin

_BUILTIN_PLUGINS: dict[ProviderId, WeatherPlugin] = {
    ProviderId.OPENWEATHER: openweather_plugin,
    ProviderId.OPEN_METEO: open_meteo_plugin,
    ProviderId.NWS: nws_plugin,
    ProviderId.WEATHERAPI: weatherapi_plugin,
    ProviderId.TOMORROW_IO: tomorrow_io_plugin,
    ProviderId.VISUAL_CROSSING: visual_crossing_plugin,
    ProviderId.WEATHERBIT: weatherbit_plugin,
    ProviderId.METEOSOURCE: meteosource_plugin,
    ProviderId.PIRATE_WEATHER: pirate_weather_plugin,
    ProviderId.MET_NORWAY: met_norway_plugin,
    ProviderId.GOOGLE_WEATHER: google_weather_plugin,
    ProviderId.STORMGLASS: stormglass_plugin,
    ProviderId.WEATHER_UNLOCKED: weather_unlocked_plugin,
}

_custom_plugins: dict[ProviderId, WeatherPlugin] = {}


def get_plugin(provider_id: ProviderId) -> WeatherPlugin | None:
    """Look up a plugin by provider ID (custom plugins take precedence)."""
    return _custom_plugins.get(provider_id) or _BUILTIN_PLUGINS.get(provider_id)


def register_plugin(plugin: WeatherPlugin) -> None:
    """Register a custom plugin (overrides built-in if same ID)."""
    _custom_plugins[plugin.id] = plugin


def list_plugins() -> list[ProviderId]:
    """List all available plugin IDs."""
    return list({*_BUILTIN_PLUGINS, *_custom_plugins})


__all__ = [
    "get_plugin",
    "google_weather_plugin",
    "list_plugins",
    "met_norway_plugin",
    "meteosource_plugin",
    "nws_plugin",
    "open_meteo_plugin",
    "openweather_plugin",
    "pirate_weather_plugin",
    "register_plugin",
    "stormglass_plugin",
    "tomorrow_io_plugin",
    "visual_crossing_plugin",
    "weather_unlocked_plugin",
    "weatherapi_plugin",
    "weatherbit_plugin",
]
