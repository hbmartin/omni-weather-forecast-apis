import asyncio
import sqlite3
from pathlib import Path


def ddl_string_parsing(definition: str | None) -> bool:
    # ruleid: sqlite-rowid-detection-requires-table-list
    return "WITHOUT ROWID" not in (definition or "").upper()


def table_list_metadata(connection: sqlite3.Connection, name: str) -> bool:
    # ok: sqlite-rowid-detection-requires-table-list
    row = connection.execute(
        "SELECT type, wr FROM pragma_table_list WHERE name = ?",
        (name,),
    ).fetchone()
    return row == ("table", 0)


def unsafe_backup(backup: str) -> None:
    def _write_backup() -> None:
        # ruleid: sqlite-backup-destination-requires-exclusive-reservation
        sqlite3.connect(backup)

    _write_backup()


def reserved_backup(backup: Path) -> None:
    # ok: sqlite-backup-destination-requires-exclusive-reservation
    def _write_backup() -> None:
        backup.touch(exist_ok=False)
        sqlite3.connect(backup)

    _write_backup()


async def unshielded_cleanup(task: asyncio.Task[None]) -> None:
    # ruleid: asyncio-shielded-task-requires-shielded-cancellation-cleanup
    try:
        await asyncio.shield(task)
    except asyncio.CancelledError:
        await task


async def shielded_cleanup(task: asyncio.Task[None]) -> None:
    while not task.done():
        # ok: asyncio-shielded-task-requires-shielded-cancellation-cleanup
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            continue
    task.result()
