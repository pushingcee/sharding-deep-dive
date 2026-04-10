# Python Utilities Restructure — Design Spec

**Date:** 2026-04-11
**Scope:** Moderate restructure of the `python/` directory — flatten package hierarchy, resolve naming collisions, remove dead code, consolidate duplicate logic.

---

## Context

The `python/` directory contains a CLI tool (`db_setup.py`) and supporting utilities for seeding a PostgreSQL database in three modes: single instance, manually sharded, and sharded with a lookup table. The code works, but has accumulated structural issues: two independent `DataGenerator` classes with the same name, two generator packages with cross-references, duplicate shard connection logic, dead code, and duplicate constants.

The goal is option 2 (moderate restructure): clean up + flatten the package hierarchy without changing the public behavior of any mode.

---

## 1. Package Layout

**Before:**
```
python/
  db_setup.py
  utilities/
    constants.py
    citus.py
    commons/
      __init__.py
      data_generator.py
      db_config.py
      queries.py
      utilities.py
    database/
      __init__.py
      database_connection_manager.py
      table_manager.py
      generators/
        __init__.py
        base.py
        single_mode_generator.py
        sharded_mode_generator.py
        sharded_lookup_mode_generator.py
    generators/
      __init__.py
      base_generator.py
```

**After:**
```
python/
  db_setup.py
  utilities/
    __init__.py
    constants.py
    config.py
    data_factory.py
    queries.py
    shard_utils.py
    connection_manager.py
    table_manager.py
    citus.py
    generators/
      __init__.py
      base.py
      single.py
      sharded.py
      sharded_lookup.py
```

The nested `commons/` and `database/` sub-packages are eliminated. The orphaned `utilities/generators/` package (which held only `base_generator.py`) is deleted entirely. One `generators/` package remains, directly inside `utilities/`.

---

## 2. File Renames and Moves

| Old path | New path | Notes |
|---|---|---|
| `utilities/commons/db_config.py` | `utilities/config.py` | |
| `utilities/commons/data_generator.py` | `utilities/data_factory.py` | Class renamed too (see §3) |
| `utilities/commons/queries.py` | `utilities/queries.py` | |
| `utilities/commons/utilities.py` | `utilities/shard_utils.py` | File only contains shard helpers |
| `utilities/database/database_connection_manager.py` | `utilities/connection_manager.py` | Drop redundant `database_` prefix |
| `utilities/database/table_manager.py` | `utilities/table_manager.py` | |
| `utilities/database/generators/base.py` | `utilities/generators/base.py` | |
| `utilities/database/generators/single_mode_generator.py` | `utilities/generators/single.py` | |
| `utilities/database/generators/sharded_mode_generator.py` | `utilities/generators/sharded.py` | |
| `utilities/database/generators/sharded_lookup_mode_generator.py` | `utilities/generators/sharded_lookup.py` | |
| `utilities/generators/base_generator.py` | deleted | Contents merged into `generators/base.py` |

---

## 3. Naming Fixes

| Current name | New name | Location | Reason |
|---|---|---|---|
| `DataGenerator` (fake data) | `DataFactory` | `data_factory.py` | Resolves collision with generator base class |
| `DataGenerator` (abstract base) | `BaseGenerator` | `generators/base.py` | Clearer purpose, no more collision |
| `ShardedModeGenerator` | `ShardedGenerator` | `generators/sharded.py` | Shorter, consistent with new filename |
| `ShardedLookupTableGenerator` | `ShardedLookupGenerator` | `generators/sharded_lookup.py` | Shorter |
| `SingleModeGenerator` | `SingleGenerator` | `generators/single.py` | Shorter, consistent |

---

## 4. Dead Code Removal

The following are removed entirely:

- `db_setup.py::generate_products_single()` — never called; `SingleGenerator.generate_products()` handles this
- `utilities/generators/base_generator.py::generate_users_with_lookup_base()` — defined but never called anywhere
- `constants.py::CHECK_IF_DB_EXISTS` — defined but never used
- `data_factory.py::STATUSES` — duplicate of `constants.py::ORDER_STATUSES`; callers use the constant instead

---

## 5. Duplicate Constant Consolidation

**`SHARD_CONFIGS`** is currently defined twice:
- `constants.py` — as the authoritative definition
- `db_setup.py` — as a local redefinition with the same values

The local definition in `db_setup.py` is removed. `db_setup.py` imports from `constants.py`.

**`STATUSES`** in `data_factory.py` duplicates `ORDER_STATUSES` in `constants.py`. The local `STATUSES` is deleted; `DataFactory` uses `ORDER_STATUSES` from constants.

**`MIN_ORDER_AMOUNT` / `MAX_ORDER_AMOUNT`** are defined in `constants.py` but `DataFactory.generate_orders_for_user()` uses hardcoded `10.0` and `3000.0`. The method is updated to use the constants.

---

## 6. Shard Connection Logic Consolidation

`connect_to_shards()` and `cleanup_connections()` are duplicated between `TableManager` and `ShardedModeGenerator` (soon `ShardedGenerator`). Both implementations are functionally identical.

These become module-level functions in `connection_manager.py`:

```python
def connect_to_shards(shard_configs, logger) -> list[Connection]: ...
def close_shard_connections(connections, logger) -> None: ...
```

Both `TableManager` and `ShardedGenerator` import and call these functions. Neither owns the logic.

---

## 7. Hardcoded Shard Count Fix

`shard_utils.py::get_shard_index()` currently hardcodes `% 4`. `DEFAULT_NUM_SHARDS = 4` exists in `constants.py` but is not used. The function is updated to accept an optional `num_shards` parameter defaulting to `DEFAULT_NUM_SHARDS`:

```python
def get_shard_index(key_uuid: UUID, num_shards: int = DEFAULT_NUM_SHARDS) -> int:
```

---

## 8. Resource Management Fix

`BaseGenerator` defines `__enter__` and `__exit__` for thread pool cleanup, but generators are never used as context managers — the thread pool is never explicitly shut down.

`db_setup.py` is updated to use generators as context managers:

```python
with SingleGenerator(db_config=DEFAULT_CONFIG) as gen:
    gen.generate_users(args.users)
    gen.generate_products(args.products)
    gen.generate_orders(args.orders_per_user, args.items_per_order)
```

This ensures the `ThreadPoolExecutor` is shut down cleanly after each run.

---

## 9. `db_setup.py` Cleanup

- Remove `generate_products_single()` (dead code)
- Remove local `SHARD_CONFIGS` (import from constants)
- Remove local `DATA_GENERATOR` instance (only existed for the now-deleted dead function)
- Drop the unused `params` parameter from `generate_data()` — each generator constructs its own `DbConfig`; `params` was passed in but ignored for sharded modes
- Use generators as context managers (see §8)

---

## 10. Import Updates

All imports across the codebase are updated to reflect the new paths. The `utilities/__init__.py` and `utilities/generators/__init__.py` export the same public names as before so that `db_setup.py` imports remain clean.

`generators/__init__.py` exports:
```python
from utilities.generators.base import BaseGenerator
from utilities.generators.single import SingleGenerator
from utilities.generators.sharded import ShardedGenerator
from utilities.generators.sharded_lookup import ShardedLookupGenerator
```

---

## Out of Scope

- No changes to SQL queries or schema
- No changes to the CLI interface (`--mode`, `--users`, etc.)
- No changes to algorithm logic inside generators (batching, threading, order generation)
- No changes to Docker/infrastructure files
- Strategy pattern / architectural pattern changes
