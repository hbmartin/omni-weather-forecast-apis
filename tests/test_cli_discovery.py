from __future__ import annotations

import asyncio
import io
import json
import os
from pathlib import Path
from types import SimpleNamespace

from rich.console import Console

from omni_weather_forecast_apis import _cli_discovery as discovery
from omni_weather_forecast_apis._cli_catalog import PROVIDER_CATALOG
from omni_weather_forecast_apis._cli_discovery import print_providers, run_doctor
from omni_weather_forecast_apis.types import (
    ErrorCode,
    ProviderError,
    ProviderErrorDetail,
    ProviderId,
)


def _console() -> tuple[Console, io.StringIO]:
    stream = io.StringIO()
    return Console(file=stream, force_terminal=False, width=260), stream


def _write_config(
    path: Path,
    *,
    providers: str = 'plugin_id = "open_meteo"\nconfig = {}',
    latitude: str = "34.2",
    longitude: str = "-117.2",
    granularities: str = '"hourly", "daily"',
    sqlite: Path | None = None,
) -> None:
    sqlite_path = sqlite or path.parent / "forecasts.sqlite"
    path.write_text(
        f"latitude = {latitude}\n"
        f"longitude = {longitude}\n"
        f"sqlite = {json.dumps(str(sqlite_path))}\n"
        f"granularity = [{granularities}]\n\n"
        "[[providers]]\n"
        f"{providers}\n",
    )
    path.chmod(0o600)


def _doctor_output(
    path: Path,
    *,
    live: bool = False,
    provider_filter=(),
) -> tuple[int, str]:
    console, stream = _console()
    exit_code = asyncio.run(
        run_doctor(
            path,
            live=live,
            provider_filter=provider_filter,
            console=console,
        ),
    )
    return exit_code, stream.getvalue()


def test_providers_prints_complete_catalog() -> None:
    console, stream = _console()

    print_providers(console=console)

    output = stream.getvalue()
    for item in PROVIDER_CATALOG:
        assert item.name in output
        assert item.provider_id.value in output
        assert item.coverage in output
        assert item.granularity_label in output
        assert item.authentication_label in output
        if item.signup_url is not None:
            assert item.signup_url in output
    assert "Open-Meteo (recommended)" in output


def test_doctor_accepts_valid_config_without_contacting_providers(
    monkeypatch,
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config.toml"
    _write_config(config_path)

    async def unexpected_live_call(*args, **kwargs):
        del args, kwargs
        raise AssertionError("static doctor contacted a provider")

    monkeypatch.setattr(discovery, "create_omni_weather", unexpected_live_call)

    exit_code, output = _doctor_output(config_path)

    assert exit_code == 0
    assert "Configuration schema" in output
    assert "Provider open_meteo" in output
    assert "settings valid" in output
    assert "FAIL" not in output


def test_doctor_reports_missing_and_malformed_config(tmp_path: Path) -> None:
    missing_code, missing_output = _doctor_output(tmp_path / "missing.toml")
    malformed = tmp_path / "malformed.toml"
    malformed.write_text("latitude = [")
    malformed_code, malformed_output = _doctor_output(malformed)

    assert missing_code == 1
    assert "not found" in missing_output
    assert malformed_code == 1
    assert "could not be parsed" in malformed_output


def test_doctor_aggregates_coordinates_duplicates_environment_and_schema(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("DOCTOR_MISSING_SECRET", raising=False)
    config_path = tmp_path / "config.toml"
    sqlite_path = tmp_path / "forecast.sqlite"
    config_path.write_text(
        "latitude = 999\n"
        f"sqlite = {json.dumps(str(sqlite_path))}\n"
        'granularity = ["daily"]\n\n'
        "[[providers]]\n"
        'plugin_id = "openweather"\n'
        'config = { api_key = "${DOCTOR_MISSING_SECRET}" }\n\n'
        "[[providers]]\n"
        'plugin_id = "openweather"\n'
        'config = { api_key = "second-key" }\n',
    )
    config_path.chmod(0o600)

    exit_code, output = _doctor_output(config_path)

    assert exit_code == 1
    assert "DOCTOR_MISSING_SECRET" in output
    assert "not set" in output
    assert "duplicates: openweather" in output
    assert "Coordinates" in output
    assert "latitude and longitude are required" in output
    assert "Configuration schema" in output
    assert "Provider openweather" in output
    assert "second-key" not in output


def test_doctor_checks_recursive_environment_references(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("DOCTOR_API_KEY", "actual-secret-value")
    config_path = tmp_path / "config.toml"
    _write_config(
        config_path,
        providers=(
            'plugin_id = "openweather"\n'
            'config = { api_key = { env = "DOCTOR_API_KEY" } }'
        ),
    )

    exit_code, output = _doctor_output(config_path)

    assert exit_code == 0
    assert "Environment DOCTOR_API_KEY" in output
    assert "set" in output
    assert "actual-secret-value" not in output


def test_recursive_environment_reference_discovery_ignores_interpolation() -> None:
    assert discovery._environment_references(
        {
            "items": ["${FIRST_SECRET}", {"nested": {"env": "SECOND_SECRET"}}],
            "unsupported": "prefix-${IGNORED_SECRET}",
        },
    ) == {"FIRST_SECRET", "SECOND_SECRET"}


def test_doctor_reports_provider_validation_without_exposing_input(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config.toml"
    _write_config(
        config_path,
        providers='plugin_id = "openweather"\nconfig = {}',
    )

    exit_code, output = _doctor_output(config_path)

    assert exit_code == 1
    assert "Provider openweather" in output
    assert "api_key" in output
    assert "input_value" not in output


def test_doctor_provider_filter_narrows_provider_checks(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("IGNORED_MISSING_KEY", raising=False)
    config_path = tmp_path / "config.toml"
    _write_config(
        config_path,
        providers=(
            'plugin_id = "open_meteo"\n'
            "config = {}\n\n"
            "[[providers]]\n"
            'plugin_id = "openweather"\n'
            'config = { api_key = "${IGNORED_MISSING_KEY}" }'
        ),
    )

    exit_code, output = _doctor_output(
        config_path,
        provider_filter=[ProviderId.OPEN_METEO],
    )

    assert exit_code == 0
    assert "Provider open_meteo" in output
    assert "IGNORED_MISSING_KEY" not in output
    assert "Provider openweather" not in output


def test_doctor_rejects_unconfigured_filter_and_incompatible_granularity(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config.toml"
    _write_config(
        config_path,
        providers=(
            'plugin_id = "met_norway"\n'
            'config = { user_agent = "WeatherLab/1.0 ops@example.org" }'
        ),
        granularities='"daily"',
    )

    incompatible_code, incompatible_output = _doctor_output(config_path)
    filtered_code, filtered_output = _doctor_output(
        config_path,
        provider_filter=[ProviderId.NWS],
    )

    assert incompatible_code == 1
    assert "Provider met_norway granularities" in incompatible_output
    assert filtered_code == 1
    assert "not enabled in the configuration" in filtered_output


def test_doctor_path_failures_and_permission_warning(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    sqlite_directory = tmp_path / "database-directory"
    sqlite_directory.mkdir()
    _write_config(config_path, sqlite=sqlite_directory)
    config_path.chmod(0o644)

    exit_code, output = _doctor_output(config_path)

    assert exit_code == 1
    assert "is a directory" in output
    if os.name != "nt":
        assert "recommended 0600" in output


def test_doctor_permission_warning_alone_retains_success(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    _write_config(config_path)
    config_path.chmod(0o644)

    exit_code, output = _doctor_output(config_path)

    assert exit_code == 0
    if os.name != "nt":
        assert "WARN" in output
        assert "recommended 0600" in output


class _LiveClient:
    def __init__(self, results) -> None:
        self.results = results
        self.request = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return None

    async def forecast(self, request):
        self.request = request
        return SimpleNamespace(results=self.results)


def test_doctor_live_check_is_opt_in_and_does_not_persist(
    monkeypatch,
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config.toml"
    _write_config(config_path)
    success = SimpleNamespace(provider=ProviderId.OPEN_METEO)
    client = _LiveClient([success])
    seen = {}

    async def fake_create(config):
        seen["config"] = config
        return client

    monkeypatch.setattr(discovery, "create_omni_weather", fake_create)

    exit_code, output = _doctor_output(config_path, live=True)

    assert exit_code == 0
    assert "Live open_meteo" in output
    assert seen["config"].sqlite is None
    assert client.request.providers == [ProviderId.OPEN_METEO]


def test_doctor_live_provider_failure_returns_one(
    monkeypatch,
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config.toml"
    _write_config(config_path)
    failure = ProviderError(
        provider=ProviderId.OPEN_METEO,
        error=ProviderErrorDetail(
            code=ErrorCode.NETWORK,
            message="simulated outage",
            latency_ms=10,
        ),
    )

    async def fake_create(config):
        del config
        return _LiveClient([failure])

    monkeypatch.setattr(discovery, "create_omni_weather", fake_create)

    exit_code, output = _doctor_output(config_path, live=True)

    assert exit_code == 1
    assert "Live open_meteo" in output
    assert "network: simulated outage" in output


def test_doctor_live_skips_statically_invalid_provider(
    monkeypatch,
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config.toml"
    _write_config(
        config_path,
        providers=(
            'plugin_id = "met_norway"\n'
            'config = { user_agent = "WeatherLab/1.0 ops@example.org" }'
        ),
        granularities='"daily"',
    )

    async def unexpected_create(config):
        del config
        raise AssertionError("invalid provider should not be contacted")

    monkeypatch.setattr(discovery, "create_omni_weather", unexpected_create)

    exit_code, output = _doctor_output(config_path, live=True)

    assert exit_code == 1
    assert "no statically valid providers selected" in output
