# Analytics Query Critique & Write-Bench Design — 2026-04-26

Two threads, captured from a design discussion:

1. What the current heavy analytics query actually measures, what it claims to measure but doesn't, and what to fix.
2. How to extend the benchmark to cover writes without inventing a 2PC story.

---

## Part 1 — Heavy Analytics Query

### 1.1 What the query is for

`java/.../repository/commons/HeavyQueryConstants.java` runs three CTEs (`user_order_stats`, `product_performance`, `country_analytics`) over date-windowed `orders` and rolls each up into one summary row. Locust drives it from `HeavyAnalyticsUser` (`benchmark/locustfile.py:202`) and `MixedWorkloadUser.occasional_analytics` (`:249`).

The intent is twofold:
- **Story A — per-shard work shrinks with shard count.** Single-DB scans N rows; each of 4 shards scans ~N/4 in parallel. Wall-clock latency drops from `T` to roughly `T/4 + fanout_overhead`. This is the pitch for sharding under read load.
- **Story B — heavy query occupies a connection.** While running, it parks one connection on each shard it touches; cheap concurrent reads queue behind it. Realistic prod failure mode ("the analytics dashboard ran and now the API is slow").

Stories A and B pull in the same direction here: sharded finishes faster *and* releases the connection sooner. That's the headline.

`pg_sleep()` cannot tell Story A — it's a fixed-time hog regardless of topology. So the heavy query is the right tool, not a workaround.

### 1.2 ~~Correctness bug in `sharded/AnalyticsService`~~ — Fixed (2026-04-28)

`sharded/AnalyticsService` and `lookup/AnalyticsService` previously fanned out the single-DB summary query to each shard and summed the per-shard summary rows — wrong for `DISTINCT` aggregates and per-group thresholds.

**Fix implemented:** replaced with `AnalyticsFanOut.java`, a coordinator-side fan-out that ships per-entity partial rows from each shard and re-aggregates at the Java layer:
- `USER_STATS_PARTIAL_SQL` — per-user GROUP BY; users are disjoint across shards so rows union cleanly.
- `PRODUCT_PARTIAL_SQL` — per-product activity slice; INNER JOIN means activity-only rows; `byProduct.size()` matches single-DB COUNT(*) semantics.
- `COUNTRY_PARTIAL_SQL` — per-country slice with `joined_row_count` to reconstruct weighted avg.
- `COUNTRY_PRODUCT_PAIRS_SQL` — SELECT DISTINCT (country, product_id) pairs; coordinator dedupes the set.

All four topologies validated to produce identical results for a June 2024 window:
```
Country Analytics: count=195, orders=47262, rev=212811958.11, special=195
Product Analytics: count=500, orders=141786, rev=538742514.79, special=499
User Analytics:    count=45795, orders=47262, rev=70937319.37, special=0
```

Note: this class duplicates aggregation logic the database already knows how to do — it is the visible, measurable cost of app-level sharding.

### 1.3 LEFT JOIN + WHERE pattern in `product_performance` — intentional

```sql
FROM products p
LEFT JOIN order_items oi ON p.product_id = oi.product_id
LEFT JOIN orders o ON oi.order_id = o.order_id
WHERE o.order_date BETWEEN ? AND ?
```

The `WHERE` predicate on `o.order_date` filters out NULL-extended rows, effectively collapsing the LEFT JOINs to INNER JOINs. Products with zero orders in the window are excluded.

This was analyzed and kept intentionally. Moving the predicate to the ON clause was attempted but produced wrong results: `order_items` joined unconditionally, so `COUNT(oi.order_id)`, `SUM(oi.quantity)`, and `SUM(oi.quantity * p.price)` computed all-time metrics instead of in-window. The current semantics — "active products in the window only" — is what the query should measure, and `PRODUCT_PARTIAL_SQL` uses an explicit INNER JOIN + WHERE to match it exactly.

### 1.4 The "cache-defeat" comment is wishful

The header comment in `HeavyQueryConstants.java` and `_random_analytics_window` claim varying the date window "exercises different slices of the heap under the full scan" and "defeats per-query result caches." Two things going on:

- **HTTP/CDN result cache:** randomization does defeat URL-keyed caches. Real, but trivial — Postgres has no query result cache to begin with.
- **Shared_buffers churn:** depends entirely on `(orders + order_items + indexes)` size vs `shared_buffers`. If the working set fits in cache (default 128 MB shared_buffers, or 25% of container RAM), random windows hit cache 99% and the "different heap slices" claim is fiction. If the working set is 3–5× shared_buffers, random windows do churn — but with `WHERE order_date BETWEEN ? AND ?` and a date index, the planner does an index range scan, not a seq scan; cache pressure profile is different again.

**To verify what's actually happening:**
```sql
EXPLAIN (ANALYZE, BUFFERS) <heavy query with sample params>;
-- look at: Buffers: shared hit=X read=Y
```
And during the run:
```sql
SELECT datname,
       blks_hit::float / NULLIF(blks_hit + blks_read, 0) AS hit_ratio
FROM pg_stat_database WHERE datname = 'mydb';
```
If hit_ratio stays >99%, the bench is measuring CPU-on-cached-data, not IO under cache pressure. Either acknowledge that in the writeup or scale the seed until `orders + order_items` is 3–5× shared_buffers.

### 1.5 Visibility threshold

For Story A to show as a clean chart, the single-DB query needs to take long enough that the parallelism delta isn't lost in noise. Suggest: time the heavy query against single-DB; if p50 < ~50ms, the sharded "T/4 + overhead" win lands in tens of ms and is hard to distinguish from network jitter. Scale the seed until single-DB p50 is in the hundreds of ms.

---

## Part 2 — Adding Writes to the Benchmark

### 2.1 What's already there

**Bulk-ingest write path** is already implemented and is itself a benchmark:

- `python/utilities/csv_loader.py:154-197` uses Postgres `COPY` for users/products/orders/order_items. Single round-trip per table, no per-row WAL flush, no per-row parsing.
- `python/utilities/generators/single.py` (and sharded/lookup variants) use multi-row INSERTs via `executemany` + parameter flattening, capped by the psycopg 65535-param ceiling, threadpooled.
- `python/utilities/csv_loader.py:215` is the lone `executemany` INSERT in the COPY path — for `user_data_shard`, deliberate exception because the table is small.

The seed-time comparison across modes already exposes:
- COPY vs multi-row INSERT throughput ratio.
- Sharded ingest gets ~4× wall-clock win on bulk because each shard's WAL writer + fsync runs in parallel.
- Single-DB threadpool parallelism plateaus due to FK row-share locks on `users`/`products` and contention on the single WAL writer. That plateau itself is a sharding argument.

**Historical context (undocumented, from author):** earlier iterations did "one INSERT per connection" and were slow; switching to batched multi-row INSERTs was the breakthrough. Worth capturing as a separate writeup — that's the kind of detail that justifies the current architecture.

### 2.2 What seed-bench cannot show

Bulk seed and live API writes are different shapes of workload:

| Axis | Bulk seed (have) | API writes (don't have) |
|---|---|---|
| Transaction size | Thousands of rows / commit | One order / commit |
| Concurrency | Few writers, big batches | Many concurrent small txns |
| Bottleneck | WAL throughput, batch efficiency | WAL **fsync rate** (commits/sec), lock waits, FK validation per commit, connection pool turnover |
| Argues | "ingestion scales" | "live OLTP throughput scales" |

The fsync-per-commit ceiling is the textbook "this is why you shard for writes" number. COPY commits once, so it cannot expose this ceiling. To demonstrate it you need many concurrent committers each doing small transactions.

### 2.3 Foundation gaps for an API write bench

Currently the Java app is read-only at the HTTP layer:

- No `POST`/`PUT`/`DELETE` endpoints on any controller (`grep '@.*Mapping' java/.../controller/`).
- `OrderRepository.save()` exists in `sharded` and `lookup` variants (`java/.../repository/sharded/OrderRepository.java:153-166`, `lookup/OrderRepository.java:177-188`) but is unreachable — pure dead code.
- No `@Transactional` anywhere.
- `save()` only writes `orders`. No `order_items` insert path. Without items, you're benching a 1-row INSERT with no FK-fanout — the trivial case.
- No idempotency / retry handling. First network blip mid-write leaves an order with no items and no rollback.

### 2.4 Design constraint: 2PC is out of scope

Modern distributed designs avoid 2PC in favor of:
- **Single-shard-by-design** — pick the shard key so that any single business operation is one shard (`user_id` here means all writes for one user are atomic by default).
- **Outbox pattern + async events** for cross-entity work.
- **Eventual consistency** for cross-shard projections.

This project should commit to that explicitly: no XA, no `PREPARE TRANSACTION`. Anything that would need 2PC is either redesigned to be single-shard or accepted as eventually consistent. Worth saying in the writeup so readers don't expect a 2PC chapter that isn't coming.

### 2.5 Stepwise plan to add API writes

**Step A — minimal POST /orders, single-shard.**

1. Add `POST /orders` to `OrderController` (all three profiles).
2. Add `OrderService.create(userId, items)` that:
   - Resolves user → shard (`ShardRouter.getShardIndex(userId)` for sharded, lookup query for lookup variant, single DB for single).
   - Wraps INSERT into `orders` + N INSERTs into `order_items` in a `@Transactional` block on the chosen DataSource.
   - N items per order should match the seed's average (`DEFAULT_ITEMS_PER_ORDER` in `python/utilities/constants.py`) to keep workload shape consistent.
3. Pick product IDs from a sampled pool (mirror the user-ID Bernoulli sampling in `locustfile.py:85`, sample products from `data/products.csv`).
4. Locust task: `POST /orders` with a user from `SAMPLE_USER_IDS` and 1–N product IDs.
5. Add `WriteHeavyUser` and update `MixedWorkloadUser` to include occasional writes.

This is the minimum that exposes WAL fsync ceiling, FK lock waits on hot users/products, and per-shard concurrent commit throughput.

**Step B — concurrent-commit axis on the seed code (no controller needed).**

Cheaper alternative or supplement to Step A: add a script that drives N concurrent connections, each doing 1-row INSERTs into `orders` + `order_items`, against each topology. Reuses `connection_manager.py` and `data_factory.py`. Strips out the HTTP/Spring layer so the measurement is pure DB.

This bridges the bulk-seed → API-writes gap cleanly: same INSERT path the seed already uses, but driven from many concurrent connections doing one row each. Shows the fsync ceiling without needing to wire controllers.

**Step C — write-read interaction.**

Once Step A is in place, run the existing read mix (`MixedWorkloadUser`) concurrently with `WriteHeavyUser`. This is where head-of-line on the connection pool, FK row-share lock waits, and Story B (heavy analytics blocking writes) all show up. The most prod-realistic chart comes from this combination.

### 2.6 New bottlenecks the writeup should call out

These appear once writes are introduced, listed by topology:

**Single-DB (the baseline being broken):**
- WAL fsync rate (the canonical write ceiling).
- Checkpoint storms — bursty writes spike IO every `checkpoint_timeout`; expect p99 latency tail-drag.
- FK row-share locks on hot `users`/`products` rows under concurrency.
- Right-edge btree contention if any time-clustered index exists on `orders` (the date index needed for the analytics query qualifies). UUID v4 PKs avoid this for the PK itself.

**Manual sharded:**
- `order_items.product_id → products(product_id)` FK forces a design decision: replicate `products` to every shard (4× write amplification on product writes), drop the FK, or hold products in a separate "reference" DB (reintroduces a single hotspot). The current seed replicates — confirm in `python/utilities/generators/sharded.py`.
- `users.email UNIQUE` is per-shard, not global. Two users with the same email can land on different shards. Any signup workload exposes this. Either accept it or build a global secondary index (essentially the lookup-table pattern keyed by email).
- Skewed write load: hashing distributes user *count* uniformly, not user *activity*. Power-user shards take disproportionate write load. Watch per-shard `pg_stat_user_tables.n_tup_ins`.
- Per-shard connection pool sizing — global write throughput is bounded by `min(shard_pool_capacity)` once any shard saturates.

**Lookup-table:**
- Lookup DB is a write hotspot for new-user creation — the central thing you sharded around is reintroduced as a write bottleneck.
- Lookup availability = global write availability. Lookup down → all writes blocked.
- Read amplification: every write requires a lookup read first. Cacheable, but the existing 77% lookup failure rate (see `2026-04-23-benchmark-action-items.md`) needs to be solved before writes are credible.

**Citus:**
- Single-shard inserts route via coordinator and are fast.
- Reference tables (for `products`) solve the FK replication problem natively. This is the strongest argument for Citus over manual sharding under writes — worth being upfront about it.
- Coordinator becomes a write-planning hotspot at high QPS.

---

## Part 3 — Connection Pooling Is the Natural Next Step

### 3.1 How we arrived here

Running benchmarks across all four topologies required raising `max_connections` multiple times. Each topology added a new kind of connection pressure:

- **Single DB** — 40 Hikari connections against 200 max; comfortable.
- **Manual sharding / Lookup** — Java routes directly to each shard; had to raise per-shard counts as concurrent load increased.
- **Citus** — workers set to 50 max_connections, matching the "sharded per-node = 0.25× single" budget. Still exhausted under load.

The Citus failure is qualitatively different. The coordinator's adaptive executor opens **up to 16 parallel connections per worker per coordinator session** (one per shard on that worker, capped by `citus.max_adaptive_executor_pool_size`). With 40 Hikari connections all active:

```
40 coordinator sessions × up to 8 shard-connections per worker = 320 attempted per worker
```

App-layer pooling (Hikari) can't solve this — the multiplication happens inside the coordinator, below the app's visibility.

### 3.2 What PgBouncer solves per topology

PgBouncer decouples client connections (cheap, many) from server connections (expensive, one process each in PostgreSQL). In **transaction pooling mode** it holds a server connection only while a transaction is active, then returns it to the pool — making it possible to serve hundreds of clients from tens of server connections.

| Topology | Where PgBouncer sits | What it solves |
|---|---|---|
| Single DB | app → PgBouncer → Postgres | Queues analytics spikes instead of timing out; lets `max_connections` stay low |
| Manual sharding | app → PgBouncer → each shard | Caps per-shard connections; smooths uneven routing load |
| Lookup table | same as manual sharding | Same; also smooths lookup-DB connection pressure |
| Citus | coordinator → PgBouncer → each worker | Kills connection multiplication; coordinator gets a bounded pool to workers regardless of Hikari pressure |

### 3.3 Benchmark implications

Adding PgBouncer sidecars to each topology's benchmark compose would answer: does pooling change the *relative* ordering between topologies, or just flatten the failure rate? Hypothesis: failure rates drop to near zero across all topologies; latency ordering unchanged; Citus benefits most because it was connection-constrained rather than CPU/IO-constrained.

PgBouncer itself adds ~0.5ms per transaction in transaction pooling mode — measurable but small relative to query latency.

This is worth adding as a variant to the project. Production deployments of any of these topologies would include a pooler; the benchmark without one understates the realistic throughput of sharded topologies.

---

## Order of operations

1. ~~Fix `sharded/AnalyticsService` aggregation correctness (1.2).~~ **Done 2026-04-28** — `AnalyticsFanOut.java`, all 4 topologies validated identical.
2. ~~Fix the `product_performance` LEFT JOIN bug (1.3).~~ **Resolved 2026-04-28** — behavior is intentional, not a bug.
3. Fix Citus seed path to call `create_distributed_table()` (was seeding with `--mode single`). **Done 2026-04-28** — `seed_and_run.sh` now uses `--mode single-shard`.
4. Add PgBouncer sidecars to benchmark composes (3.3) — prerequisite for a fair Citus benchmark.
5. Run `EXPLAIN (ANALYZE, BUFFERS)` and check `pg_stat_database.blks_hit` ratio (1.4). Either accept the result or scale seed until cache pressure is real.
6. Confirm single-DB heavy-query p50 is in the hundreds of ms (1.5). Scale seed if not.
7. Add concurrent-commit script (Step B in 2.5) — fastest path to a write story.
8. Add `POST /orders` + `@Transactional` order-create (Step A) — full API write bench.
9. Run mixed read+write workload (Step C) — most prod-realistic chart.
10. Capture the historical bulk-seed concurrency learnings (insert-per-connection → batched) as a separate doc — that work is real and currently undocumented.
