# sqlit -> sqlagent backend integration plan (current phase)

This document tracks the backend-only integration phase where selected `sqlit` connection/discovery capabilities are brought into `sqlagent` with minimal logic drift.

## Scope and constraints

- Keep copied logic close to upstream `sqlit` behavior.
- Focus on backend path only (no full Textual UI integration/cleanup in this phase).
- Support one active database target at a time.
- Persist active target as a SQLAlchemy URI.
- Allow Docker auto-discovered credentials to be persisted as plain text for now.
- Use a compatibility shim strategy for `sqlit.*` imports.

## Execution plan

1. Restore backend import compatibility for copied `dbcore` modules.
2. Add startup flow in CLI to choose DB target before agent graph loads.
3. Persist selected target to local config.
4. Wire DB tools to read active URI from config instead of hardcoded SQLite path.
5. Validate with import smoke checks and syntax checks.

## What was implemented

### 1) Compatibility shim for `sqlit.*` imports

- Added `src/sqlit/` compatibility package so existing `dbcore` imports resolve without mass rewriting.
- Kept key backend wiring compatible by:
  - aliasing `sqlit.domains.connections` to `dbcore.connections`,
  - adding wrappers for `sqlit.shared.app.runtime` and `sqlit.shared.app.services`,
  - vendoring selected `sqlit` shared/query/shell modules required by backend flows.

### 2) Persistent database URI config

- Refactored `src/config/db_config.py` to JSON-backed config at `~/.sqlagent/config.json`.
- Added:
  - `database_uri` key storage,
  - fallback default URI from local Chinook SQLite DB,
  - helpers to get/set URI and normalize SQLite path -> URI.

### 3) Pre-agent DB target selection in CLI

- Updated `src/main.py` startup flow to configure DB target before importing/building the agent.
- Added options:
  - SQLite file path,
  - direct SQLAlchemy URI,
  - Docker auto discovery,
  - keep current target.
- Docker mode:
  - detects available containers,
  - shows connectable running DB containers,
  - converts selected connection to SQLAlchemy URI for supported DB types.

### 4) Database tool uses active config URI

- Updated `src/tools/database.py` to initialize `SQLDatabase` from `DBConfig().get_database_uri()`.
- Removed dependence on hardcoded local SQLite file path.

## Verification completed

- Import smoke checks passed for core compatibility paths (connections catalog/discovery/session/runtime/services/history/settings).
- Cloud compatibility imports (aws/azure paths) also loaded.
- Python syntax compile over `src/**/*.py` passed.

## Remaining work (this phase)

- Runtime validation in a full environment with optional deps installed:
  - run `python src/main.py`,
  - test each config mode (SQLite path / direct URI / Docker discovery),
  - confirm agent queries execute against selected target.

## Known limitations

- Docker -> SQLAlchemy URI conversion currently supports `sqlite`, `duckdb`, `postgresql`, `mysql`, and `mariadb`.
- Unsupported discovered DB types currently return explicit errors.
- This phase does not implement multi-profile connection switching UI/state; only one active URI is persisted.
