from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from omni_weather_forecast_apis.types import Granularity, ProviderId

type AuthenticationKind = Literal[
    "none",
    "identity",
    "api_key",
    "app_credentials",
    "jwt",
]


@dataclass(frozen=True)
class CredentialField:
    """One provider setting collected by the setup wizard."""

    config_key: str
    prompt: str
    password: bool = True


@dataclass(frozen=True)
class ProviderSetup:
    """CLI-facing provider metadata used for setup and discovery."""

    provider_id: ProviderId
    name: str
    coverage: str
    granularities: tuple[Granularity, ...]
    authentication: AuthenticationKind
    signup_url: str | None = None
    credential_fields: tuple[CredentialField, ...] = ()
    recommended: bool = False

    @property
    def authentication_label(self) -> str:
        match self.authentication:
            case "none":
                return "None"
            case "identity":
                return "Contact identity"
            case "api_key":
                return "API key"
            case "app_credentials":
                return "App ID + key"
            case "jwt":
                return "Signed JWT (key file)"

    @property
    def granularity_label(self) -> str:
        return ", ".join(item.value for item in self.granularities)


_ALL = (Granularity.MINUTELY, Granularity.HOURLY, Granularity.DAILY)
_HOURLY_DAILY = (Granularity.HOURLY, Granularity.DAILY)
_HOURLY = (Granularity.HOURLY,)
_API_KEY = (CredentialField("api_key", "API key"),)

PROVIDER_CATALOG: tuple[ProviderSetup, ...] = (
    ProviderSetup(
        ProviderId.OPEN_METEO,
        "Open-Meteo",
        "Global",
        _ALL,
        "none",
        recommended=True,
    ),
    ProviderSetup(
        ProviderId.MET_NORWAY,
        "MET Norway",
        "Nordics",
        _HOURLY,
        "identity",
    ),
    ProviderSetup(
        ProviderId.NWS,
        "NWS / NOAA",
        "US only",
        _HOURLY_DAILY,
        "identity",
    ),
    ProviderSetup(
        ProviderId.NBM,
        "NOAA NBM",
        "US only",
        _HOURLY,
        "none",
        credential_fields=(
            CredentialField("station_id", "Station ID", password=False),
        ),
    ),
    ProviderSetup(
        ProviderId.OPENWEATHER,
        "OpenWeather",
        "Global",
        _ALL,
        "api_key",
        "https://home.openweathermap.org/users/sign_up",
        _API_KEY,
    ),
    ProviderSetup(
        ProviderId.WEATHERAPI,
        "WeatherAPI.com",
        "Global",
        _HOURLY_DAILY,
        "api_key",
        "https://www.weatherapi.com/signup.aspx",
        _API_KEY,
    ),
    ProviderSetup(
        ProviderId.TOMORROW_IO,
        "Tomorrow.io",
        "Global",
        _ALL,
        "api_key",
        "https://app.tomorrow.io/signup",
        _API_KEY,
    ),
    ProviderSetup(
        ProviderId.VISUAL_CROSSING,
        "Visual Crossing",
        "Global",
        _HOURLY_DAILY,
        "api_key",
        "https://www.visualcrossing.com/sign-up",
        _API_KEY,
    ),
    ProviderSetup(
        ProviderId.WEATHERBIT,
        "Weatherbit",
        "Global",
        _HOURLY_DAILY,
        "api_key",
        "https://www.weatherbit.io/account/create",
        _API_KEY,
    ),
    ProviderSetup(
        ProviderId.METEOSOURCE,
        "Meteosource",
        "Global",
        _ALL,
        "api_key",
        "https://public-web.meteosource.com/client/sign-up",
        _API_KEY,
    ),
    ProviderSetup(
        ProviderId.PIRATE_WEATHER,
        "Pirate Weather",
        "Global",
        _ALL,
        "api_key",
        "https://pirate-weather.apiable.io/",
        _API_KEY,
    ),
    ProviderSetup(
        ProviderId.STORMGLASS,
        "Stormglass",
        "Global",
        _HOURLY,
        "api_key",
        "https://dashboard.stormglass.io/register",
        _API_KEY,
    ),
    ProviderSetup(
        ProviderId.GOOGLE_WEATHER,
        "Google Weather",
        "Global",
        _HOURLY_DAILY,
        "api_key",
        "https://developers.google.com/maps/documentation/weather/get-api-key",
        _API_KEY,
    ),
    ProviderSetup(
        ProviderId.MET_OFFICE,
        "Met Office",
        "Global",
        _HOURLY_DAILY,
        "api_key",
        "https://datahub.metoffice.gov.uk/",
        _API_KEY,
    ),
    ProviderSetup(
        ProviderId.XWEATHER,
        "Xweather",
        "Global",
        _HOURLY_DAILY,
        "app_credentials",
        "https://signup.xweather.com/",
        (
            CredentialField("client_id", "Client ID"),
            CredentialField("client_secret", "Client secret"),
        ),
    ),
    ProviderSetup(
        ProviderId.WEATHERKIT,
        "Apple WeatherKit",
        "Global",
        _ALL,
        "jwt",
        "https://developer.apple.com/weatherkit/get-started/",
        (
            CredentialField("team_id", "Apple Developer Team ID"),
            CredentialField("service_id", "WeatherKit service ID"),
            CredentialField("key_id", "Key ID"),
            CredentialField("private_key_path", "Path to the .p8 private key"),
        ),
    ),
)

PROVIDER_BY_ID: dict[ProviderId, ProviderSetup] = {
    item.provider_id: item for item in PROVIDER_CATALOG
}


def supports_any(
    provider_id: ProviderId,
    granularities: tuple[Granularity, ...] | list[Granularity],
) -> bool:
    """Return whether a provider supports at least one requested granularity."""

    supported = PROVIDER_BY_ID[provider_id].granularities
    return any(item in supported for item in granularities)


__all__ = [
    "PROVIDER_BY_ID",
    "PROVIDER_CATALOG",
    "CredentialField",
    "ProviderSetup",
    "supports_any",
]
