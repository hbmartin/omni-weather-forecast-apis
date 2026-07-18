import sqlite3

db_path = '/Users/haroldmartin/Downloads/imagemine/omni-weather-forecast-apis/gem_compare_ratings.sqlite'
conn = sqlite3.connect(db_path)
conn.execute('''
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
''')
conn.commit()
conn.close()
