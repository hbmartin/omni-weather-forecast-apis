from __future__ import annotations

import importlib
import logging
import shlex
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType, SimpleNamespace

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
    ProviderError,
    ProviderErrorDetail,
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


def _run_cli_capturing_request(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    argv: list[str],
    config_body: str | None = None,
) -> ForecastRequest:
    """Run main() with a stubbed client; return the ForecastRequest it built."""

    stub = _ArchiveStubClient()

    async def fake_create(
        config: object,
        **kwargs: object,
    ) -> _ArchiveStubClient:
        del config, kwargs
        return stub

    monkeypatch.setattr(cli, "create_omni_weather", fake_create)
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        config_body or '[[providers]]\nplugin_id = "open_meteo"\nconfig = {}\n',
    )
    exit_code = cli.main(
        ["--config", str(config_path), "--lat", "34.0", "--lon", "-118.0", *argv],
    )
    assert exit_code == 0
    assert isinstance(stub.request, ForecastRequest)
    return stub.request


_PROVIDER_BLOCK = '[[providers]]\nplugin_id = "open_meteo"\nconfig = {}\n'


def _config_with(top_level: str) -> str:
    """Build a TOML body; root keys must precede the [[providers]] array-of-tables."""

    return f"{top_level}\n{_PROVIDER_BLOCK}"


def test_config_values_reach_the_forecast_request(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    request = _run_cli_capturing_request(
        monkeypatch,
        tmp_path,
        [],
        config_body=_config_with(
            'granularity = ["minutely"]\n'
            'language = "de"\n'
            "default_timeout_ms = 4200.0\n",
        ),
    )

    assert request.granularity == [Granularity.MINUTELY]
    assert request.language == "de"
    assert request.timeout_ms == 4200.0


def test_cli_flags_override_config_values(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    request = _run_cli_capturing_request(
        monkeypatch,
        tmp_path,
        ["--language", "fr", "--timeout-ms", "999"],
        config_body=_config_with('language = "de"\ndefault_timeout_ms = 4200.0\n'),
    )

    assert request.language == "fr"
    assert request.timeout_ms == 999.0


def test_granularity_flag_replaces_rather_than_merges_config(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    request = _run_cli_capturing_request(
        monkeypatch,
        tmp_path,
        ["--granularity", "daily"],
        config_body=_config_with('granularity = ["minutely", "hourly"]\n'),
    )

    assert request.granularity == [Granularity.DAILY]


def test_config_include_raw_applies_without_a_flag(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Config acts as a baseline the CLI flag can only enable, never disable."""

    request = _run_cli_capturing_request(
        monkeypatch,
        tmp_path,
        [],
        config_body=_config_with("include_raw = true\n"),
    )

    assert request.include_raw is True


def test_defaults_apply_when_neither_cli_nor_config_sets_them(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    request = _run_cli_capturing_request(monkeypatch, tmp_path, [])

    assert request.granularity == [Granularity.HOURLY, Granularity.DAILY]
    assert request.language == "en"
    assert request.include_raw is False


def _failing_response() -> ForecastResponse:
    return ForecastResponse(
        request=ForecastResponseRequest(
            latitude=34.0,
            longitude=-118.0,
            granularity=[Granularity.HOURLY],
            language="en",
        ),
        results=[
            ProviderError(
                provider=ProviderId.OPEN_METEO,
                error=ProviderErrorDetail(
                    code=ErrorCode.NETWORK,
                    message="connection reset",
                    latency_ms=12.0,
                ),
            ),
        ],
        summary=ForecastResponseSummary(total=1, succeeded=0, failed=1),
        completed_at=datetime(2026, 7, 13, 12, 0, tzinfo=UTC),
        total_latency_ms=12.0,
    )


@pytest.mark.parametrize("printer", ["_print_results", "_print_results_plain"])
def test_provider_failures_are_mirrored_to_stderr(
    capsys: pytest.CaptureFixture[str],
    printer: str,
) -> None:
    getattr(cli, printer)(_failing_response(), None, None)

    captured = capsys.readouterr()
    assert "provider open_meteo failed: network: connection reset" in captured.err
    # The typed error code is diagnosable from stdout too, not just the message.
    assert "network" in captured.out


def test_rich_fallback_reports_each_failure_exactly_once(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """_print_results delegates to the plain printer; only one of them may emit."""

    real_import = importlib.import_module

    def no_rich(name: str, package: str | None = None) -> ModuleType:
        if name.startswith("rich."):
            raise ImportError(name)
        return real_import(name, package)

    monkeypatch.setattr(cli.importlib, "import_module", no_rich)
    cli._print_results(_failing_response(), None, None)

    err = capsys.readouterr().err
    assert err.count("provider open_meteo failed: network: connection reset") == 1


def test_explicit_missing_config_reports_a_targeted_error(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    missing = tmp_path / "config directory" / "absent $(unsafe).toml"

    assert cli.main(["--config", str(missing), "--lat", "1", "--lon", "2"]) == 2

    err = capsys.readouterr().err
    assert f"error: config file not found: {missing}" in err
    assert (
        f"run: omni-weather init --config {shlex.quote(str(missing))}"
        in err.splitlines()
    )
    assert "No such file or directory" not in err


def test_explicit_directory_config_is_not_reported_missing(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert cli.main(["--config", str(tmp_path), "--lat", "1", "--lon", "2"]) == 2

    err = capsys.readouterr().err
    assert "config file not found" not in err
    assert "omni-weather init" not in err


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


@pytest.mark.parametrize(
    ("provider_ids", "granularities", "expected"),
    [
        ({ProviderId.WEATHERKIT}, [Granularity.MINUTELY], True),
        ({ProviderId.WEATHERKIT}, [Granularity.HOURLY], True),
        ({ProviderId.WEATHERKIT}, [], False),
        ({ProviderId.TOMORROW_IO}, [Granularity.DAILY], True),
        ({ProviderId.TOMORROW_IO}, [Granularity.HOURLY], False),
        ({ProviderId.OPEN_METEO}, [Granularity.HOURLY, Granularity.DAILY], False),
    ],
)
def test_cli_needs_timezone_lookup(
    provider_ids: set[ProviderId],
    granularities: list[Granularity],
    expected: bool,
) -> None:
    assert cli._cli_needs_timezone_lookup(provider_ids, granularities) is expected
