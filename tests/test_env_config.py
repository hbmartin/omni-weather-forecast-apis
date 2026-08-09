"""Tests for environment-variable placeholder resolution."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from omni_weather_forecast_apis.client import OmniWeatherClient
from omni_weather_forecast_apis.types import (
    ErrorCode,
    ForecastRequest,
    OmniWeatherConfig,
    ProviderId,
    ProviderRegistration,
)
from omni_weather_forecast_apis.utils import (
    EnvVarNotSetError,
    resolve_env_placeholders,
)
from tests.helpers import CountingInstance, FactoryPlugin


def test_resolves_whole_string_placeholder(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OWFA_TEST_KEY", "secret-value")

    resolved = resolve_env_placeholders({"api_key": "${OWFA_TEST_KEY}"})

    assert resolved == {"api_key": "secret-value"}


def test_resolves_env_marker_table(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OWFA_TEST_KEY", "secret-value")

    resolved = resolve_env_placeholders({"api_key": {"env": "OWFA_TEST_KEY"}})

    assert resolved == {"api_key": "secret-value"}


def test_resolves_nested_structures(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OWFA_TEST_KEY", "secret-value")

    resolved = resolve_env_placeholders(
        {"outer": {"keys": ["${OWFA_TEST_KEY}", "literal"]}},
    )

    assert resolved == {"outer": {"keys": ["secret-value", "literal"]}}


def test_leaves_plain_values_untouched() -> None:
    config = {"api_key": "plain", "days": 7, "flag": True, "ratio": 1.5}

    assert resolve_env_placeholders(config) == config


def test_partial_interpolation_is_not_supported() -> None:
    config = {"user_agent": "MyApp/${VERSION}"}

    assert resolve_env_placeholders(config) == config


def test_missing_variable_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OWFA_MISSING_KEY", raising=False)

    with pytest.raises(EnvVarNotSetError, match="OWFA_MISSING_KEY"):
        resolve_env_placeholders({"api_key": "${OWFA_MISSING_KEY}"})


def test_missing_variable_becomes_provider_init_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OWFA_MISSING_KEY", raising=False)

    class DummyPlugin:
        @property
        def id(self) -> ProviderId:
            return ProviderId.OPENWEATHER

        @property
        def name(self) -> str:
            return "dummy"

        def validate_config(self, config: dict[str, Any]) -> dict[str, Any]:
            return config

        async def initialize(self, config: dict[str, Any]) -> Any:
            del config
            raise AssertionError("initialize should not be reached")

    client = OmniWeatherClient(
        OmniWeatherConfig(
            providers=[
                ProviderRegistration(
                    plugin_id=ProviderId.OPENWEATHER,
                    config={"api_key": "${OWFA_MISSING_KEY}"},
                ),
            ],
        ),
        plugins=[DummyPlugin()],
    )

    async def scenario() -> tuple[str, str]:
        await client.initialize()
        response = await client.forecast(ForecastRequest(latitude=34, longitude=-118))
        await client.close()
        result = response.results[0]
        assert result.status == "error"
        return result.error.code.value, result.error.message

    code, message = asyncio.run(scenario())

    assert code == ErrorCode.NOT_AVAILABLE.value
    assert "OWFA_MISSING_KEY" in message


def test_list_placeholders_resolve_into_key_variants(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OWFA_KEY_ONE", "v1")
    monkeypatch.setenv("OWFA_KEY_TWO", "v2")
    seen_keys: list[str] = []

    def factory(config: dict[str, Any]) -> CountingInstance:
        seen_keys.append(config["api_key"])
        return CountingInstance()

    client = OmniWeatherClient(
        OmniWeatherConfig(
            providers=[
                ProviderRegistration(
                    plugin_id=ProviderId.OPEN_METEO,
                    config={"api_key": ["${OWFA_KEY_ONE}", "${OWFA_KEY_TWO}"]},
                ),
            ],
        ),
        plugins=[FactoryPlugin(ProviderId.OPEN_METEO, factory)],
    )

    asyncio.run(client.initialize())

    assert seen_keys == ["v1", "v2"]


def test_unset_list_placeholder_is_provider_init_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OWFA_KEY_ONE", "v1")
    monkeypatch.delenv("OWFA_MISSING_KEY", raising=False)

    client = OmniWeatherClient(
        OmniWeatherConfig(
            providers=[
                ProviderRegistration(
                    plugin_id=ProviderId.OPEN_METEO,
                    config={"api_key": ["${OWFA_KEY_ONE}", "${OWFA_MISSING_KEY}"]},
                ),
            ],
        ),
        plugins=[
            FactoryPlugin(ProviderId.OPEN_METEO, lambda _config: CountingInstance()),
        ],
    )

    async def scenario() -> tuple[str, str]:
        await client.initialize()
        response = await client.forecast(ForecastRequest(latitude=34, longitude=-118))
        await client.close()
        result = response.results[0]
        assert result.status == "error"
        return result.error.code.value, result.error.message

    code, message = asyncio.run(scenario())

    assert code == ErrorCode.NOT_AVAILABLE.value
    assert "OWFA_MISSING_KEY" in message
