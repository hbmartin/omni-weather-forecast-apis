"""Daily request-quota tracking for providers with per-day call limits."""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from collections.abc import Callable
from contextlib import closing
from datetime import date
from pathlib import Path
from threading import Lock
from typing import Protocol, runtime_checkable

from omni_weather_forecast_apis.types import ProviderId

_MISSING_TABLE_ERROR = "no such table"
_CREATE_SCHEMA_SQL = """
    CREATE TABLE IF NOT EXISTS provider_quota_usage (
        provider TEXT NOT NULL,
        day TEXT NOT NULL,
        request_count INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (provider, day)
    )
"""
_SELECT_USAGE_SQL = """
    SELECT request_count FROM provider_quota_usage
    WHERE provider = ? AND day = ?
"""
_INCREMENT_USAGE_SQL = """
    INSERT INTO provider_quota_usage (provider, day, request_count)
    VALUES (?, ?, 1)
    ON CONFLICT (provider, day)
    DO UPDATE SET request_count = request_count + 1
"""


@runtime_checkable
class QuotaTracker(Protocol):
    """Tracks how many requests were sent per provider per UTC day."""

    def get_usage(self, provider: ProviderId, day: date) -> int:
        """Return the number of requests recorded for a provider on a day."""
        ...

    def record_request(self, provider: ProviderId, day: date) -> None:
        """Record one request for a provider on a day."""
        ...

    def try_consume(self, provider: ProviderId, day: date, limit: int) -> bool:
        """Record one request only when the provider has remaining quota."""
        ...


class InMemoryQuotaTracker:
    """Process-local quota tracker; state is lost when the process exits."""

    def __init__(self) -> None:
        self._usage: dict[tuple[ProviderId, date], int] = defaultdict(int)
        self._lock = Lock()

    def get_usage(self, provider: ProviderId, day: date) -> int:
        with self._lock:
            return self._usage[(provider, day)]

    def record_request(self, provider: ProviderId, day: date) -> None:
        with self._lock:
            self._usage[(provider, day)] += 1

    def try_consume(self, provider: ProviderId, day: date, limit: int) -> bool:
        """Record one request only when the provider has remaining quota."""

        with self._lock:
            key = (provider, day)
            if self._usage[key] >= limit:
                return False
            self._usage[key] += 1
            return True


class SqliteQuotaTracker:
    """Quota tracker persisted in SQLite so limits survive across runs.

    The CLI reuses the forecast database, giving free-tier daily caps
    (e.g. OpenWeather's 1,000 calls/day) durable enforcement.
    """

    def __init__(self, database_path: str | Path) -> None:
        self._database_path = database_path
        self._schema_ready = False

    def get_usage(self, provider: ProviderId, day: date) -> int:
        def read(connection: sqlite3.Connection) -> int:
            row = connection.execute(
                _SELECT_USAGE_SQL,
                (provider.value, day.isoformat()),
            ).fetchone()
            return int(row[0]) if row is not None else 0

        return self._run(read)

    def record_request(self, provider: ProviderId, day: date) -> None:
        def increment(connection: sqlite3.Connection) -> None:
            connection.execute(
                _INCREMENT_USAGE_SQL,
                (provider.value, day.isoformat()),
            )
            connection.commit()

        self._run(increment)

    def try_consume(self, provider: ProviderId, day: date, limit: int) -> bool:
        """Atomically reserve one daily request when quota remains."""

        def consume(connection: sqlite3.Connection) -> bool:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                _SELECT_USAGE_SQL,
                (provider.value, day.isoformat()),
            ).fetchone()
            usage = int(row[0]) if row is not None else 0
            if usage >= limit:
                connection.rollback()
                return False
            connection.execute(
                _INCREMENT_USAGE_SQL,
                (provider.value, day.isoformat()),
            )
            connection.commit()
            return True

        return self._run(consume)

    def _run[T](self, operation: Callable[[sqlite3.Connection], T]) -> T:
        """Run an operation, recreating the schema once if it went missing."""

        try:
            with closing(self._connect()) as connection:
                return operation(connection)
        except sqlite3.OperationalError as exc:
            if _MISSING_TABLE_ERROR not in str(exc):
                raise
        # The database file was deleted or rotated out from under a long-lived
        # tracker, so the cached "schema exists" flag is stale.
        self._schema_ready = False
        with closing(self._connect()) as connection:
            return operation(connection)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database_path, timeout=10.0)
        connection.execute("PRAGMA busy_timeout = 10000")
        if not self._schema_ready:
            connection.execute(_CREATE_SCHEMA_SQL)
            connection.commit()
            self._schema_ready = True
        return connection


__all__ = ["InMemoryQuotaTracker", "QuotaTracker", "SqliteQuotaTracker"]
