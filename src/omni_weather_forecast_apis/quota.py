"""Daily request-quota tracking for providers with per-day call limits."""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from contextlib import closing
from datetime import date
from pathlib import Path
from typing import Protocol, runtime_checkable

from omni_weather_forecast_apis.types import ProviderId


@runtime_checkable
class QuotaTracker(Protocol):
    """Tracks how many requests were sent per provider per UTC day."""

    def get_usage(self, provider: ProviderId, day: date) -> int:
        """Return the number of requests recorded for a provider on a day."""
        ...

    def record_request(self, provider: ProviderId, day: date) -> None:
        """Record one request for a provider on a day."""
        ...


class InMemoryQuotaTracker:
    """Process-local quota tracker; state is lost when the process exits."""

    def __init__(self) -> None:
        self._usage: dict[tuple[ProviderId, date], int] = defaultdict(int)

    def get_usage(self, provider: ProviderId, day: date) -> int:
        return self._usage[(provider, day)]

    def record_request(self, provider: ProviderId, day: date) -> None:
        self._usage[(provider, day)] += 1


class SqliteQuotaTracker:
    """Quota tracker persisted in SQLite so limits survive across runs.

    The CLI reuses the forecast database, giving free-tier daily caps
    (e.g. OpenWeather's 1,000 calls/day) durable enforcement.
    """

    def __init__(self, database_path: str | Path) -> None:
        self._database_path = database_path

    def get_usage(self, provider: ProviderId, day: date) -> int:
        with closing(self._connect()) as connection:
            row = connection.execute(
                """
                SELECT request_count FROM provider_quota_usage
                WHERE provider = ? AND day = ?
                """,
                (provider.value, day.isoformat()),
            ).fetchone()
        return int(row[0]) if row is not None else 0

    def record_request(self, provider: ProviderId, day: date) -> None:
        with closing(self._connect()) as connection:
            connection.execute(
                """
                INSERT INTO provider_quota_usage (provider, day, request_count)
                VALUES (?, ?, 1)
                ON CONFLICT (provider, day)
                DO UPDATE SET request_count = request_count + 1
                """,
                (provider.value, day.isoformat()),
            )
            connection.commit()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database_path)
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS provider_quota_usage (
                provider TEXT NOT NULL,
                day TEXT NOT NULL,
                request_count INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (provider, day)
            )
            """,
        )
        return connection


__all__ = ["InMemoryQuotaTracker", "QuotaTracker", "SqliteQuotaTracker"]
