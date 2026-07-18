"""NOAA/NWS National Blend of Models adapter (via the IEM MOS archive).

The NBM is NOAA's operational bias-corrected, ensemble-calibrated blend of
dozens of model inputs — the institutional version of what a downstream
grounding/blending pipeline builds, which makes it both a strong input source
and the benchmark to beat. NCEP publishes NBM station bulletins only as
~28 MB whole-network text files per cycle, so this adapter reads the Iowa
Environmental Mesonet's parsed per-station archive of the NBS bulletin
(short range, 3-hourly out to +72 h) instead: one small JSON request per
fetch, no API key.

Units per the NBM v4.2 text card: TMP/DPT °F, WSP/GST knots, SKY %, P06 %.
Two deliberate omissions:

- ``P06`` is a 6-hour PoP — broader than an hourly PoP. It is still mapped to
  ``precipitation_probability`` (providers differ in PoP windows anyway, and
  downstream calibration owns the correction), but the window is documented.
- ``Q06`` (6-hour accumulation) is NOT mapped to hourly ``precipitation``:
  a 6-hour total attributed to a single 3-hourly point would double-count in
  any hourly aggregation. Amounts can come from a gridded NBM reader later.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from pydantic import Field

from omni_weather_forecast_apis.mapping.units import (
    celsius_from_fahrenheit,
    ms_from_knots,
)
from omni_weather_forecast_apis.plugins._base import (
    BasePlugin,
    BasePluginInstance,
    as_float,
    build_hourly_point,
    build_source_forecast,
    normalize_percent,
    probability_from_percent_value,
)
from omni_weather_forecast_apis.types import (
    ErrorCode,
    PluginCapabilities,
    PluginFetchParams,
    PluginFetchResult,
    ProviderId,
    WeatherDataPoint,
)
from omni_weather_forecast_apis.types.plugin import ProviderConfigModel

if TYPE_CHECKING:
    import httpx2


class NBMConfig(ProviderConfigModel):
    """The NBM is station-indexed: ``station_id`` is the NBM/METAR site whose
    bulletin stands in for the requested coordinates (e.g. ``KSBD``)."""

    station_id: str = Field(min_length=4, max_length=8, pattern=r"^[A-Z0-9]+$")


_BASE_URL = "https://mesonet.agron.iastate.edu/api/1/mos.json"
_MODEL = "NBS"
# Text-bulletin sentinels (e.g. CIG -88 "unlimited") must never leak into
# physical fields; anything at or below this is treated as missing.
_SENTINEL_FLOOR = -80.0
_CAPABILITIES = PluginCapabilities(
    granularity_minutely=False,
    granularity_hourly=True,
    granularity_daily=False,
    max_horizon_hourly_hours=72.0,
    requires_api_key=False,
    coverage="us_only",
)


def _physical(value: Any) -> float | None:
    numeric = as_float(value)
    if numeric is None or numeric <= _SENTINEL_FLOOR:
        return None
    return numeric


def _converted(
    value: Any,
    convert: Callable[[float], float],
) -> float | None:
    numeric = _physical(value)
    if numeric is None:
        return None
    return float(convert(numeric))


def _hourly_point(row: dict[str, Any]) -> WeatherDataPoint | None:
    timestamp = row.get("ftime_utc") or row.get("ftime")
    if not isinstance(timestamp, str):
        return None
    return build_hourly_point(
        timestamp,
        temperature=_converted(row.get("tmp"), celsius_from_fahrenheit),
        dew_point=_converted(row.get("dpt"), celsius_from_fahrenheit),
        wind_speed=_converted(row.get("wsp"), ms_from_knots),
        wind_gust=_converted(row.get("gst"), ms_from_knots),
        wind_direction=_physical(row.get("wdr")),
        cloud_cover=normalize_percent(_physical(row.get("sky"))),
        precipitation_probability=probability_from_percent_value(
            _physical(row.get("p06")),
        ),
    )


def _latest_run_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The endpoint returns the latest run; filter defensively anyway."""
    runtimes = [
        runtime
        for row in rows
        if isinstance(runtime := row.get("runtime_utc") or row.get("runtime"), str)
    ]
    if not runtimes:
        return []
    latest = max(runtimes)
    return [
        row for row in rows if (row.get("runtime_utc") or row.get("runtime")) == latest
    ]


class _NBMInstance(BasePluginInstance[NBMConfig]):
    """Configured NBM instance."""

    def __init__(self, config: NBMConfig) -> None:
        super().__init__(ProviderId.NBM, config, _CAPABILITIES)

    async def fetch_forecast(
        self,
        params: PluginFetchParams,
        client: httpx2.AsyncClient,
    ) -> PluginFetchResult:
        payload, error = await self._get_json(
            client,
            _BASE_URL,
            params={"station": self.config.station_id, "model": _MODEL},
        )
        if error is not None:
            return error
        rows = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(rows, list):
            return self._error(
                ErrorCode.PARSE,
                "IEM MOS payload has no data table",
                raw=payload if params.include_raw else None,
            )
        try:
            hourly = [
                point
                for row in sorted(
                    _latest_run_rows([r for r in rows if isinstance(r, dict)]),
                    key=lambda r: str(r.get("ftime_utc") or r.get("ftime")),
                )
                if (point := _hourly_point(row)) is not None
            ]
        except (KeyError, TypeError, ValueError) as exc:
            return self._error(
                ErrorCode.PARSE,
                f"Failed to parse NBM payload: {exc}",
                raw=payload if params.include_raw else None,
            )
        return self._success(
            [
                build_source_forecast(
                    self.provider_id,
                    timezone=params.timezone,
                    hourly=hourly,
                ),
            ],
            raw=payload if params.include_raw else None,
        )


class _NBMPlugin(BasePlugin[NBMConfig]):
    """NBM plugin facade."""

    config_model = NBMConfig
    instance_cls = _NBMInstance
    _id = ProviderId.NBM
    _name = "NOAA National Blend of Models"


nbm_plugin = _NBMPlugin()

__all__ = ["NBMConfig", "nbm_plugin"]
