from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def rounded_coordinate(value: float) -> str:
    """Return the coordinate precision used for timezone lookups and caching."""

    return f"{value:.4f}"


def zoneinfo_from_name(value: object) -> ZoneInfo | None:
    """Load a non-empty IANA timezone name when it is available locally."""

    if not isinstance(value, str) or not (name := value.strip()):
        return None
    try:
        return ZoneInfo(name)
    except (ValueError, ZoneInfoNotFoundError):
        return None


def validate_timezone_name(value: str) -> str:
    """Validate and normalize a public IANA timezone-name field."""

    if (location_timezone := zoneinfo_from_name(value)) is None:
        raise ValueError(f"timezone must be a loadable IANA name, got {value!r}")
    return location_timezone.key


def localize_wall_time(naive_iso: str, location_timezone: ZoneInfo) -> datetime:
    """Attach an IANA timezone to an unambiguous, existent local wall time."""

    naive = datetime.fromisoformat(naive_iso)
    if naive.tzinfo is not None:
        raise ValueError("local wall time must not include an offset")

    first = naive.replace(tzinfo=location_timezone, fold=0)
    second = naive.replace(tzinfo=location_timezone, fold=1)
    first_valid = (
        first.astimezone(UTC).astimezone(location_timezone).replace(tzinfo=None)
        == naive
    )
    second_valid = (
        second.astimezone(UTC).astimezone(location_timezone).replace(tzinfo=None)
        == naive
    )
    if not first_valid and not second_valid:
        raise ValueError(
            f"nonexistent local time {naive_iso} in {location_timezone.key}"
        )
    if first_valid and second_valid and first.utcoffset() != second.utcoffset():
        raise ValueError(f"ambiguous local time {naive_iso} in {location_timezone.key}")
    return first if first_valid else second


def resolve_wall_time(naive_iso: str, location_timezone: ZoneInfo) -> datetime:
    """Resolve a local wall time to a real instant without ever raising on DST.

    Unlike :func:`localize_wall_time`, DST discontinuities are tolerated so a
    single bad hour never discards a whole payload:

    * Ambiguous times (fall-back) resolve to the earlier ``fold=0``
      (pre-transition) occurrence.
    * Nonexistent times (spring-forward gap) resolve to a valid instant by
      round-tripping the ``fold=0`` reading through UTC, which lands on the
      real post-gap moment.
    * Unambiguous, existent times behave like :func:`localize_wall_time`.
    """

    naive = datetime.fromisoformat(naive_iso)
    if naive.tzinfo is not None:
        raise ValueError("local wall time must not include an offset")

    candidate = naive.replace(tzinfo=location_timezone, fold=0)
    round_tripped = candidate.astimezone(UTC).astimezone(location_timezone)
    if round_tripped.replace(tzinfo=None) == naive:
        return candidate
    return round_tripped


__all__ = [
    "localize_wall_time",
    "resolve_wall_time",
    "rounded_coordinate",
    "validate_timezone_name",
    "zoneinfo_from_name",
]
