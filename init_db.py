import sqlite3
from pathlib import Path

DEFAULT_DATABASE_PATH = Path(__file__).resolve().parent / "gem_compare_ratings.sqlite"
_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS commit_ratings (
  feature_name TEXT NOT NULL,
  model TEXT NOT NULL,
  commit_hash TEXT NOT NULL,
  category TEXT NOT NULL,
  score INTEGER NOT NULL CHECK (score BETWEEN 0 AND 3),
  rationale TEXT NOT NULL,
  compared_at_utc TEXT NOT NULL,
  baseline_commit TEXT NOT NULL,
  PRIMARY KEY (feature_name, model, commit_hash, category)
);
"""


def initialize_database(database_path: Path = DEFAULT_DATABASE_PATH) -> None:
    connection = sqlite3.connect(database_path)
    try:
        connection.execute(_CREATE_TABLE_SQL)
        connection.commit()
    finally:
        connection.close()


def main() -> None:
    initialize_database()


if __name__ == "__main__":
    main()
