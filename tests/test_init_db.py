from __future__ import annotations

import sqlite3
from pathlib import Path

import init_db


def test_default_database_path_is_relative_to_script() -> None:
    expected = Path(init_db.__file__).resolve().parent / "gem_compare_ratings.sqlite"

    assert expected == init_db.DEFAULT_DATABASE_PATH


def test_initialize_database_creates_commit_ratings_table(tmp_path: Path) -> None:
    database_path = tmp_path / "nested" / "gem_compare_ratings.sqlite"
    database_path.parent.mkdir()

    init_db.initialize_database(database_path)
    init_db.initialize_database(database_path)

    connection = sqlite3.connect(database_path)
    try:
        table_sql = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?",
            ("commit_ratings",),
        ).fetchone()
    finally:
        connection.close()

    assert table_sql is not None
    assert "PRIMARY KEY (feature_name, model, commit_hash, category)" in table_sql[0]
