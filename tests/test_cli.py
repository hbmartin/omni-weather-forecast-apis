from __future__ import annotations

import importlib
import logging

import pytest

from omni_weather_forecast_apis import cli
from omni_weather_forecast_apis.cli import (
    _resolve_optional,
    _resolve_required,
    _setup_debug_logging,
    build_parser,
)
from omni_weather_forecast_apis.types import ErrorCode, ProviderId, ProviderLogEvent


def test_resolve_required_preserves_zero_values() -> None:
    assert _resolve_required(0.0, 51.5, "lat") == 0.0
    assert _resolve_required(0.0, -0.1, "lon") == 0.0


def test_resolve_required_exits_when_both_sources_are_missing() -> None:
    with pytest.raises(SystemExit) as exc_info:
        _resolve_required(None, None, "lat")

    assert exc_info.value.code == 2


def test_resolve_optional_preserves_explicit_values() -> None:
    assert _resolve_optional("en", "de") == "en"
    assert _resolve_optional(0.0, 5000.0) == 0.0


def test_build_parser_leaves_language_unset_until_resolution() -> None:
    parsed = build_parser().parse_args([])

    assert parsed.language is None


def test_build_parser_defaults_to_table_format() -> None:
    parsed = build_parser().parse_args([])

    assert parsed.output_format == "table"


def test_build_parser_accepts_json_format() -> None:
    parsed = build_parser().parse_args(["--format", "json"])

    assert parsed.output_format == "json"


def test_build_parser_rejects_unknown_format() -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args(["--format", "yaml"])


def test_sqlite_is_optional() -> None:
    parsed = build_parser().parse_args([])

    assert parsed.sqlite is None


def test_debug_logging_falls_back_to_stdlib_without_loguru(
    monkeypatch,
    tmp_path,
    capsys,
):
    real_import_module = importlib.import_module

    def fake_import_module(name, *args, **kwargs):
        if name == "loguru":
            raise ImportError("No module named 'loguru'")
        return real_import_module(name, *args, **kwargs)

    monkeypatch.setattr(cli.importlib, "import_module", fake_import_module)
    log_path = tmp_path / "debug.log"

    hook = _setup_debug_logging(log_path)

    captured = capsys.readouterr()
    assert "loguru is not installed" in captured.err
    assert "omni-weather-forecast-apis[cli]" in captured.err

    hook(
        ProviderLogEvent(
            provider=ProviderId.OPEN_METEO,
            phase="error",
            message="boom",
            error_code=ErrorCode.NETWORK,
        ),
    )
    hook(
        ProviderLogEvent(
            provider=ProviderId.OPEN_METEO,
            phase="success",
            message="done: 18°C",
        ),
    )

    file_handler = next(
        handler
        for handler in logging.getLogger(
            "omni_weather_forecast_apis.cli.debug"
        ).handlers
        if isinstance(handler, logging.FileHandler)
    )
    assert file_handler.encoding == "utf-8"

    contents = log_path.read_text(encoding="utf-8")
    assert "boom" in contents
    assert "done: 18°C" in contents
