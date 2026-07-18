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

INSERT INTO commit_ratings (feature_name, model, commit_hash, category, score, rationale, compared_at_utc, baseline_commit) VALUES
('universal weather forecast aggregation library', 'Claude', 'ef7f91f4903b84ab218affa33cdbde968cb6591e', 'Product & Feature Completeness', 2, 'Implements CLI and aggregation but SQLite persistence is just an unnormalized JSON dump. Strong test coverage is a plus.', datetime('now'), '5845bee7fbeb4839bd3264e12ef3e5138fc6f892')
ON CONFLICT DO UPDATE SET score=excluded.score, rationale=excluded.rationale, compared_at_utc=excluded.compared_at_utc, baseline_commit=excluded.baseline_commit;

INSERT INTO commit_ratings (feature_name, model, commit_hash, category, score, rationale, compared_at_utc, baseline_commit) VALUES
('universal weather forecast aggregation library', 'Claude', 'ef7f91f4903b84ab218affa33cdbde968cb6591e', 'Hexagonal Architectural Alignment', 2, 'Good plugin protocol structure, but core HTTP client and error mapping logic heavily leaks into each individual plugin.', datetime('now'), '5845bee7fbeb4839bd3264e12ef3e5138fc6f892')
ON CONFLICT DO UPDATE SET score=excluded.score, rationale=excluded.rationale, compared_at_utc=excluded.compared_at_utc, baseline_commit=excluded.baseline_commit;

INSERT INTO commit_ratings (feature_name, model, commit_hash, category, score, rationale, compared_at_utc, baseline_commit) VALUES
('universal weather forecast aggregation library', 'Claude', 'ef7f91f4903b84ab218affa33cdbde968cb6591e', 'TypeScript Quality', 3, 'Excellent Python typing with frozen ConfigDicts on data models, strict StrEnum usage, and explicit Pydantic 3.14 compatibility patch.', datetime('now'), '5845bee7fbeb4839bd3264e12ef3e5138fc6f892')
ON CONFLICT DO UPDATE SET score=excluded.score, rationale=excluded.rationale, compared_at_utc=excluded.compared_at_utc, baseline_commit=excluded.baseline_commit;

INSERT INTO commit_ratings (feature_name, model, commit_hash, category, score, rationale, compared_at_utc, baseline_commit) VALUES
('universal weather forecast aggregation library', 'Claude', 'ef7f91f4903b84ab218affa33cdbde968cb6591e', 'Data Safety & Security', 2, 'Avoids logging API keys securely, but SQLite storage writes raw JSON blobs which is not as safe or structured for long-term data warehousing.', datetime('now'), '5845bee7fbeb4839bd3264e12ef3e5138fc6f892')
ON CONFLICT DO UPDATE SET score=excluded.score, rationale=excluded.rationale, compared_at_utc=excluded.compared_at_utc, baseline_commit=excluded.baseline_commit;

INSERT INTO commit_ratings (feature_name, model, commit_hash, category, score, rationale, compared_at_utc, baseline_commit) VALUES
('universal weather forecast aggregation library', 'Claude', 'ef7f91f4903b84ab218affa33cdbde968cb6591e', 'Error Handling & Side-Effect Safety', 1, 'Duplicate error handling across all 13 plugins. Relies on catch-all try/except blocks in the orchestrator.', datetime('now'), '5845bee7fbeb4839bd3264e12ef3e5138fc6f892')
ON CONFLICT DO UPDATE SET score=excluded.score, rationale=excluded.rationale, compared_at_utc=excluded.compared_at_utc, baseline_commit=excluded.baseline_commit;

INSERT INTO commit_ratings (feature_name, model, commit_hash, category, score, rationale, compared_at_utc, baseline_commit) VALUES
('universal weather forecast aggregation library', 'Claude', 'ef7f91f4903b84ab218affa33cdbde968cb6591e', 'System Resilience & Blast Radius', 2, 'Includes basic global semaphores and rate limiters but lacks granularly stacked provider limits or isolated timeout domains.', datetime('now'), '5845bee7fbeb4839bd3264e12ef3e5138fc6f892')
ON CONFLICT DO UPDATE SET score=excluded.score, rationale=excluded.rationale, compared_at_utc=excluded.compared_at_utc, baseline_commit=excluded.baseline_commit;

INSERT INTO commit_ratings (feature_name, model, commit_hash, category, score, rationale, compared_at_utc, baseline_commit) VALUES
('universal weather forecast aggregation library', 'Claude', 'ef7f91f4903b84ab218affa33cdbde968cb6591e', 'Performance & Scalability', 2, 'Utilizes asyncio.gather efficiently, though rate limit mechanisms could become a bottleneck under high multi-provider load without composite scaling.', datetime('now'), '5845bee7fbeb4839bd3264e12ef3e5138fc6f892')
ON CONFLICT DO UPDATE SET score=excluded.score, rationale=excluded.rationale, compared_at_utc=excluded.compared_at_utc, baseline_commit=excluded.baseline_commit;

INSERT INTO commit_ratings (feature_name, model, commit_hash, category, score, rationale, compared_at_utc, baseline_commit) VALUES
('universal weather forecast aggregation library', 'Claude', 'ef7f91f4903b84ab218affa33cdbde968cb6591e', 'Complexity & Maintainability & Project Convention Adherence', 1, 'Highly WET (Write Everything Twice) implementation with repetitive HTTP and parsing logic scattered across 13 identical plugin classes.', datetime('now'), '5845bee7fbeb4839bd3264e12ef3e5138fc6f892')
ON CONFLICT DO UPDATE SET score=excluded.score, rationale=excluded.rationale, compared_at_utc=excluded.compared_at_utc, baseline_commit=excluded.baseline_commit;

INSERT INTO commit_ratings (feature_name, model, commit_hash, category, score, rationale, compared_at_utc, baseline_commit) VALUES
('universal weather forecast aggregation library', 'Claude', 'ef7f91f4903b84ab218affa33cdbde968cb6591e', 'Testability & Observability', 3, 'Comprehensive suite of 97 tests covering edge cases. Standard logging properly implemented across orchestration and plugin execution.', datetime('now'), '5845bee7fbeb4839bd3264e12ef3e5138fc6f892')
ON CONFLICT DO UPDATE SET score=excluded.score, rationale=excluded.rationale, compared_at_utc=excluded.compared_at_utc, baseline_commit=excluded.baseline_commit;

INSERT INTO commit_ratings (feature_name, model, commit_hash, category, score, rationale, compared_at_utc, baseline_commit) VALUES
('universal weather forecast aggregation library', 'Claude', 'ef7f91f4903b84ab218affa33cdbde968cb6591e', 'Business Logic', 2, 'Perfect handling of Open-Meteo multi-model suffixes, but failed to apply SI unit conversions (e.g., visibility remained in meters instead of km).', datetime('now'), '5845bee7fbeb4839bd3264e12ef3e5138fc6f892')
ON CONFLICT DO UPDATE SET score=excluded.score, rationale=excluded.rationale, compared_at_utc=excluded.compared_at_utc, baseline_commit=excluded.baseline_commit;

INSERT INTO commit_ratings (feature_name, model, commit_hash, category, score, rationale, compared_at_utc, baseline_commit) VALUES
('universal weather forecast aggregation library', 'Codex', '5845bee7fbeb4839bd3264e12ef3e5138fc6f892', 'Product & Feature Completeness', 3, 'Ships a fully normalized 7-table SQLite database representing the complete multi-provider time-series schema alongside robust CLI processing.', datetime('now'), 'ef7f91f4903b84ab218affa33cdbde968cb6591e')
ON CONFLICT DO UPDATE SET score=excluded.score, rationale=excluded.rationale, compared_at_utc=excluded.compared_at_utc, baseline_commit=excluded.baseline_commit;

INSERT INTO commit_ratings (feature_name, model, commit_hash, category, score, rationale, compared_at_utc, baseline_commit) VALUES
('universal weather forecast aggregation library', 'Codex', '5845bee7fbeb4839bd3264e12ef3e5138fc6f892', 'Hexagonal Architectural Alignment', 3, 'Stellar use of a generic BasePluginInstance abstraction that tightly isolates protocol-level HTTP concerns from domain-level mapping.', datetime('now'), 'ef7f91f4903b84ab218affa33cdbde968cb6591e')
ON CONFLICT DO UPDATE SET score=excluded.score, rationale=excluded.rationale, compared_at_utc=excluded.compared_at_utc, baseline_commit=excluded.baseline_commit;

INSERT INTO commit_ratings (feature_name, model, commit_hash, category, score, rationale, compared_at_utc, baseline_commit) VALUES
('universal weather forecast aggregation library', 'Codex', '5845bee7fbeb4839bd3264e12ef3e5138fc6f892', 'TypeScript Quality', 2, 'Great use of Python Generic[ConfigT] and schemas, but lost the Python 3.14 compatibility patch and removed immutability guards (frozen=True) from responses.', datetime('now'), 'ef7f91f4903b84ab218affa33cdbde968cb6591e')
ON CONFLICT DO UPDATE SET score=excluded.score, rationale=excluded.rationale, compared_at_utc=excluded.compared_at_utc, baseline_commit=excluded.baseline_commit;

INSERT INTO commit_ratings (feature_name, model, commit_hash, category, score, rationale, compared_at_utc, baseline_commit) VALUES
('universal weather forecast aggregation library', 'Codex', '5845bee7fbeb4839bd3264e12ef3e5138fc6f892', 'Data Safety & Security', 3, 'Highly structured relational storage in SQLite protects against malformed payloads and implicitly validates data shape before persistence.', datetime('now'), 'ef7f91f4903b84ab218affa33cdbde968cb6591e')
ON CONFLICT DO UPDATE SET score=excluded.score, rationale=excluded.rationale, compared_at_utc=excluded.compared_at_utc, baseline_commit=excluded.baseline_commit;

INSERT INTO commit_ratings (feature_name, model, commit_hash, category, score, rationale, compared_at_utc, baseline_commit) VALUES
('universal weather forecast aggregation library', 'Codex', '5845bee7fbeb4839bd3264e12ef3e5138fc6f892', 'Error Handling & Side-Effect Safety', 3, 'Centralized HTTP error mapping, strict JSON decode guards, and robust per-provider granular exception translation preventing system crashes.', datetime('now'), 'ef7f91f4903b84ab218affa33cdbde968cb6591e')
ON CONFLICT DO UPDATE SET score=excluded.score, rationale=excluded.rationale, compared_at_utc=excluded.compared_at_utc, baseline_commit=excluded.baseline_commit;

INSERT INTO commit_ratings (feature_name, model, commit_hash, category, score, rationale, compared_at_utc, baseline_commit) VALUES
('universal weather forecast aggregation library', 'Codex', '5845bee7fbeb4839bd3264e12ef3e5138fc6f892', 'System Resilience & Blast Radius', 3, 'CompositeRateLimiter intelligently manages global concurrency alongside provider-specific RPS bounds. Strict timeouts isolated via asyncio.timeout.', datetime('now'), 'ef7f91f4903b84ab218affa33cdbde968cb6591e')
ON CONFLICT DO UPDATE SET score=excluded.score, rationale=excluded.rationale, compared_at_utc=excluded.compared_at_utc, baseline_commit=excluded.baseline_commit;

INSERT INTO commit_ratings (feature_name, model, commit_hash, category, score, rationale, compared_at_utc, baseline_commit) VALUES
('universal weather forecast aggregation library', 'Codex', '5845bee7fbeb4839bd3264e12ef3e5138fc6f892', 'Performance & Scalability', 3, 'Highly efficient processing decoupled by _base.py utilities. Advanced rate limiting ensures seamless horizontal scaling across APIs.', datetime('now'), 'ef7f91f4903b84ab218affa33cdbde968cb6591e')
ON CONFLICT DO UPDATE SET score=excluded.score, rationale=excluded.rationale, compared_at_utc=excluded.compared_at_utc, baseline_commit=excluded.baseline_commit;

INSERT INTO commit_ratings (feature_name, model, commit_hash, category, score, rationale, compared_at_utc, baseline_commit) VALUES
('universal weather forecast aggregation library', 'Codex', '5845bee7fbeb4839bd3264e12ef3e5138fc6f892', 'Complexity & Maintainability & Project Convention Adherence', 3, 'Exceptional DRY approach by refactoring 13 plugins to utilize a shared facade, cutting significant boilerplate and minimizing surface area for bugs.', datetime('now'), 'ef7f91f4903b84ab218affa33cdbde968cb6591e')
ON CONFLICT DO UPDATE SET score=excluded.score, rationale=excluded.rationale, compared_at_utc=excluded.compared_at_utc, baseline_commit=excluded.baseline_commit;

INSERT INTO commit_ratings (feature_name, model, commit_hash, category, score, rationale, compared_at_utc, baseline_commit) VALUES
('universal weather forecast aggregation library', 'Codex', '5845bee7fbeb4839bd3264e12ef3e5138fc6f892', 'Testability & Observability', 0, 'Deleted almost all unit tests (dropped from 97 to 11) and completely removed standard Python logging, making the orchestration system entirely silent/unobservable.', datetime('now'), 'ef7f91f4903b84ab218affa33cdbde968cb6591e')
ON CONFLICT DO UPDATE SET score=excluded.score, rationale=excluded.rationale, compared_at_utc=excluded.compared_at_utc, baseline_commit=excluded.baseline_commit;

INSERT INTO commit_ratings (feature_name, model, commit_hash, category, score, rationale, compared_at_utc, baseline_commit) VALUES
('universal weather forecast aggregation library', 'Codex', '5845bee7fbeb4839bd3264e12ef3e5138fc6f892', 'Business Logic', 2, 'Accurately handled SI unit coercion (visibility to km) via shared helpers, but broke Open-Meteo multi-model payload parsing by assuming an array structure.', datetime('now'), 'ef7f91f4903b84ab218affa33cdbde968cb6591e')
ON CONFLICT DO UPDATE SET score=excluded.score, rationale=excluded.rationale, compared_at_utc=excluded.compared_at_utc, baseline_commit=excluded.baseline_commit;
