from __future__ import annotations

from pathlib import Path

import platformdirs

_APP_NAME = "omni-weather"
_CONFIG_FILE_NAME = "config.toml"
_SQLITE_FILE_NAME = "forecasts.sqlite"


def normalized_path(path: Path | str) -> Path:
    """Expand user markers and make a CLI path stable across working directories."""

    return Path(path).expanduser().resolve()


def default_config_path() -> Path:
    """Return the platform-native default configuration file path."""

    directory = platformdirs.user_config_path(_APP_NAME, appauthor=False)
    return directory / _CONFIG_FILE_NAME


def default_sqlite_path() -> Path:
    """Return the platform-native default SQLite output path."""

    directory = platformdirs.user_data_path(_APP_NAME, appauthor=False)
    return directory / _SQLITE_FILE_NAME


def legacy_config_path() -> Path:
    """Return the pre-platformdirs CLI configuration location."""

    return Path.home() / ".config" / "omni_weather_forecast_apis.toml"


def find_config_path(explicit: Path | None) -> Path | None:
    """Resolve an explicit, platform, or legacy config without inventing a file."""

    if explicit is not None:
        return normalized_path(explicit)
    if (platform_path := default_config_path()).is_file():
        return platform_path
    if (legacy_path := legacy_config_path()).is_file():
        return legacy_path
    return None


def init_target_path(explicit: Path | None) -> Path:
    """Choose the file edited by explicit setup or first-run setup."""

    return find_config_path(explicit) or default_config_path()


__all__ = [
    "default_config_path",
    "default_sqlite_path",
    "find_config_path",
    "init_target_path",
    "legacy_config_path",
    "normalized_path",
]
