from __future__ import annotations

import importlib
import logging
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from omni_weather_forecast_apis import cli
from omni_weather_forecast_apis._cli_timezone_cache import TimezoneResolution
from omni_weather_forecast_apis.cli import (
    _resolve_optional,
    _resolve_required,
    _setup_debug_logging,
    build_parser,
)
from omni_weather_forecast_apis.types import (
    ErrorCode,
    ForecastRequest,
    ForecastResponse,
    ForecastResponseRequest,
    ForecastResponseSummary,
    Granularity,
    ProviderId,
    ProviderLogEvent,
)


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


class _ArchiveStubClient:
    def __init__(self) -> None:
        self.request: object | None = None
        self._response = ForecastResponse(
            request=ForecastResponseRequest(
                latitude=34.0,
                longitude=-118.0,
                granularity=[],
                language="en",
            ),
            results=[],
            summary=ForecastResponseSummary(total=0, succeeded=0, failed=0),
            completed_at=datetime(2026, 7, 13, 12, 0, tzinfo=UTC),
            total_latency_ms=1.0,
        )

    async def __aenter__(self) -> _ArchiveStubClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    async def forecast(self, request: object) -> object:
        self.request = request
        return self._response


def _run_cli_capturing_config(monkeypatch, tmp_path, argv, config_body=None):
    """Run main() with a stubbed client; return the config it received."""

    captured: dict[str, object] = {}

    async def fake_create(config, **kwargs):
        del kwargs
        captured["config"] = config
        return _ArchiveStubClient()

    monkeypatch.setattr(cli, "create_omni_weather", fake_create)
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        config_body or '[[providers]]\nplugin_id = "open_meteo"\nconfig = {}\n',
    )
    exit_code = cli.main(
        ["--config", str(config_path), "--lat", "34.0", "--lon", "-118.0", *argv],
    )
    assert exit_code == 0
    return captured["config"]


def test_sqlite_enables_raw_archive_with_run_scoped_path(
    monkeypatch,
    tmp_path,
) -> None:
    db_path = tmp_path / "forecasts.sqlite"
    config = _run_cli_capturing_config(
        monkeypatch,
        tmp_path,
        ["--sqlite", str(db_path)],
    )

    archive_path = config.http.raw_archive_path
    assert archive_path is not None
    assert archive_path.startswith(str(tmp_path / "raw"))
    assert archive_path.endswith(".jsonl.gz")


def test_default_raw_archive_path_is_unique_for_same_start_time(
    monkeypatch,
    tmp_path,
) -> None:
    started_at = datetime(2024, 1, 2, 3, 4, 5, 678901, tzinfo=UTC)
    suffixes = iter(("a" * 32, "b" * 32))
    monkeypatch.setattr(cli, "utc_now", lambda: started_at)
    monkeypatch.setattr(
        cli,
        "uuid4",
        lambda: SimpleNamespace(hex=next(suffixes)),
    )

    first = cli._default_raw_archive_path(tmp_path / "forecasts.sqlite")
    second = cli._default_raw_archive_path(tmp_path / "forecasts.sqlite")

    assert first.name == "20240102T030405.678901Z-aaaaaaaaaaaa.jsonl.gz"
    assert second.name == "20240102T030405.678901Z-bbbbbbbbbbbb.jsonl.gz"
    assert first != second


def test_no_raw_archive_flag_disables_archiving(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "forecasts.sqlite"
    config = _run_cli_capturing_config(
        monkeypatch,
        tmp_path,
        ["--sqlite", str(db_path), "--no-raw-archive"],
    )

    assert config.http.raw_archive_path is None


def test_raw_archive_requires_sqlite(monkeypatch, tmp_path) -> None:
    config = _run_cli_capturing_config(monkeypatch, tmp_path, [])

    assert config.http.raw_archive_path is None


def test_raw_archive_config_kill_switch(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "forecasts.sqlite"
    config = _run_cli_capturing_config(
        monkeypatch,
        tmp_path,
        ["--sqlite", str(db_path)],
        config_body=(
            "[http]\nraw_archive_enabled = false\n\n"
            '[[providers]]\nplugin_id = "open_meteo"\nconfig = {}\n'
        ),
    )

    assert config.http.raw_archive_path is None


def test_cli_passes_cached_timezone_to_library_request(monkeypatch, tmp_path) -> None:
    database_path = tmp_path / "forecasts.sqlite"
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        '[[providers]]\nplugin_id = "tomorrow_io"\nconfig = { api_key = "test" }\n',
        encoding="utf-8",
    )
    client = _ArchiveStubClient()
    resolution_call: dict[str, object] = {}

    async def fake_create(*_args, **_kwargs):
        return client

    async def fake_resolve(
        database: Path,
        latitude: float,
        longitude: float,
        *,
        needs_lookup: bool,
        client: _ArchiveStubClient,
    ) -> TimezoneResolution:
        resolution_call.update(
            database=database,
            latitude=latitude,
            longitude=longitude,
            needs_lookup=needs_lookup,
            client=client,
        )
        return TimezoneResolution("America/Los_Angeles")

    monkeypatch.setattr(cli, "create_omni_weather", fake_create)
    monkeypatch.setattr(cli, "resolve_cli_timezone", fake_resolve)

    exit_code = cli.main(
        [
            "--config",
            str(config_path),
            "--lat",
            "34.0",
            "--lon",
            "-118.0",
            "--sqlite",
            str(database_path),
            "--granularity",
            "daily",
        ],
    )

    assert exit_code == 0
    assert resolution_call == {
        "database": database_path,
        "latitude": 34.0,
        "longitude": -118.0,
        "needs_lookup": True,
        "client": client,
    }
    assert isinstance(client.request, ForecastRequest)
    assert client.request.timezone == "America/Los_Angeles"
    assert client.request.granularity == [Granularity.DAILY]
