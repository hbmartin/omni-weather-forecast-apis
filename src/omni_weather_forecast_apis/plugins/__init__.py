"""Provider plugin registry."""

from __future__ import annotations

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
from omni_weather_forecast_apis.types import ProviderId, WeatherPlugin

REGISTERED_PLUGINS: tuple[WeatherPlugin, ...] = (
    openweather_plugin,
    open_meteo_plugin,
    nws_plugin,
    weatherapi_plugin,
    tomorrow_io_plugin,
    visual_crossing_plugin,
    weatherbit_plugin,
    meteosource_plugin,
    pirate_weather_plugin,
    met_norway_plugin,
    google_weather_plugin,
    stormglass_plugin,
    weather_unlocked_plugin,
)
PLUGIN_REGISTRY: dict[ProviderId, WeatherPlugin] = {
    plugin.id: plugin for plugin in REGISTERED_PLUGINS
}


def get_plugin(plugin_id: ProviderId) -> WeatherPlugin:
    """Look up a plugin by identifier."""

    return PLUGIN_REGISTRY[plugin_id]


def get_plugin_registry() -> dict[ProviderId, WeatherPlugin]:
    """Return a shallow copy of the registry."""

    return dict(PLUGIN_REGISTRY)


def register_plugin(plugin: WeatherPlugin) -> None:
    """Register or override a plugin implementation."""

    PLUGIN_REGISTRY[plugin.id] = plugin


__all__ = [
    "PLUGIN_REGISTRY",
    "REGISTERED_PLUGINS",
    "get_plugin",
    "get_plugin_registry",
    "google_weather_plugin",
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
