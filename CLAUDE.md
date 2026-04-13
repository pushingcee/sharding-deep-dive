# Claude Code Instructions

## Git Rules

- **Do not run git commit, git push, git amend, or any destructive git commands**
- `git mv` is allowed for renaming/moving files
- The user reviews all changes and commits manually
- Stage files with `git add` only when the user explicitly asks

## Project Overview

A PostgreSQL sharding/partitioning demo project. The `python/` directory contains a CLI tool (`db_setup.py`) for seeding a database in three modes:

- `single` — one PostgreSQL instance, serial PKs
- `sharded` — 4 PostgreSQL instances, app-level UUID routing via hash
- `sharded-lookup-table` — 4 shards + a central lookup table mapping user UUIDs to shard IDs

## Python Stack

- Python 3.13
- `psycopg` (v3) + `psycopg-pool` for database access
- `Faker` for fake data generation
- `mypy --strict` is the linter — all code must pass it clean
- Virtual env at `python/.venv` or `python/venv`

## Typing Standard

- `mypy --strict` is enforced (see `python/mypy.ini`)
- Every function and method must have fully annotated signatures, including inner functions
- `namedtuple` → use `typing.NamedTuple` for mypy compatibility
- No bare `Any` without a `# type: ignore` comment explaining why
- Run `cd python && mypy .` to verify

## Active Restructure (see spec)

A moderate restructure is in progress. Spec at:
`docs/superpowers/specs/2026-04-11-python-restructure-design.md`

Key changes:
- Flatten `utilities/commons/` and `utilities/database/` into `utilities/`
- Rename `DataGenerator` (fake data) → `DataFactory`, base class → `BaseGenerator`
- Single `utilities/generators/` package (delete old `utilities/generators/base_generator.py`)
- Move shard connection logic to `utilities/connection_manager.py`
- Remove all dead code and duplicate constants

## Docker

Each mode has its own `docker-compose.yaml` in numbered directories:
- `00-single-db/`
- `01-manual-sharding/`
- `02-citus-sharding/`
- `03-manual-sharding-lookup-table/`

Benchmark compose files are in `*.benchmark.yaml` variants.
