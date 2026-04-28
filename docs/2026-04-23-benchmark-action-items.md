# Benchmark Action Items — 2026-04-23

Follow-up issues uncovered by the 2026-04-22/23 benchmark runs in `benchmark/results/`. Each item is independent and tracked separately below.

Run files referenced:
- `single_20260422_235328_*` — 5.6% failures, mostly healthy
- `sharded_20260422_235643_*` — 53% failures, under-seeded (data-volume bug, fix already applied)
- `citus_20260423_000007_*` — 98% failures, cluster non-functional
- `lookup_20260423_000346_*` — 63% failures, under-seeded + slow fan-out

---

## 1. Re-seed all four strategies with USERS_MULTI=1M

**Status:** ready — config change is applied, blocked on stale volumes.

**Context:** `benchmark/seed_and_run.sh:20` now defaults `USERS_MULTI=1000000`. With existing SHA1 hash routing this distributes ~250k users per shard, matching single-DB total data → apples-to-apples on dataset size. The `DB_USER_COUNT` env var hack in `benchmark/locustfile.py` was reverted in the same change.

**Blocker:** running `./seed_and_run.sh --seed` over an existing volume fails with `duplicate key value violates unique constraint "products_pkey"`. Cause: `python/utilities/queries.py` uses `CREATE TABLE IF NOT EXISTS`, and `docker compose down` does not remove volumes. Prior seed's data persists and conflicts with the new COPY.

**Fix:** in `benchmark/seed_and_run.sh`, when `--seed` is set, run `dc -f "$COMPOSE" down -v` before `dc -f "$COMPOSE" up -d` for each strategy's seed step. `--seed` semantically means "start clean."

**Workaround until fix is applied:**
```sh
docker compose -f 00-single-db/docker-compose.yaml down -v
docker compose -f 01-manual-sharding/docker-compose.yaml down -v
docker compose -f 02-citus-sharding/docker-compose-sharded-citus.yaml down -v
docker compose -f 03-manual-sharding-lookup-table/docker-compose.yaml down -v
./benchmark/seed_and_run.sh --seed
```

**Verification:**
- Each sharded strategy logs `Shard N: loaded ~250,000 users.` (1M ÷ 4 ± hash skew).
- `docker exec shard1 psql -U postgres -d mydb -c "SELECT count(*) FROM users;"` returns ~250k.
- Post-run `_failures.csv`: `/users/{uuid}` and `/orders/{uuid}` 404 counts drop to near zero.

---

## 2. Citus cluster non-functional — investigate

**Status:** open, root cause unknown.

**Symptom:** in `citus_20260423_000007_stats.csv` every endpoint's median response time is exactly 10000ms (= the Locust client timeout). 1112/1133 requests failed (98%). This is not a 404/data-volume issue — requests are not returning at all.

**Hypothesis:** `citus_configure()` in `benchmark/seed_and_run.sh:137-151` runs after a benchmark-compose restart and re-registers workers via `citus_add_node`. Every command in that function uses `2>/dev/null || true`, so silent failures are masked. Workers may not actually be registered at query time, so the coordinator can't route to shards.

**Investigation steps:**
1. Read `benchmark/results/citus_20260423_000007_db.log` and `citus_20260423_000007_spring.log` — look for connection refused / timeout / `ERROR: could not connect to node` lines from the coordinator.
2. After `citus_configure`, manually verify worker state:
   ```sh
   docker exec master psql -U postgres -d mydb -c "SELECT * FROM pg_dist_node;"
   docker exec master psql -U postgres -d mydb -c "SELECT * FROM citus_check_cluster_node_health();"
   ```
   Expect 4 active workers, all healthy.
3. Check whether the benchmark compose file reuses the same volumes as the seed compose file. If volumes diverge, the seeded shard data isn't visible to the benchmark cluster.
4. Remove the `2>/dev/null || true` swallowing in `citus_configure` so failures surface in the script log instead of being hidden.

**Likely fixes:**
- Remove silent error suppression in `citus_configure`.
- Add a post-configure assertion: query `pg_dist_node` and fail if fewer than 4 workers are active.
- Verify benchmark and seed compose files mount the same named volumes for master + workers.

---

## 3. `/orders/all-page` 100% failure on single-DB — investigate

**Status:** open, scope of breakage unclear.

**Symptom:** in `single_20260422_235328_stats.csv`, `/orders/all-page` shows 102 requests / 102 failures (100%). Every other endpoint on the same single-DB run had reasonable success rates, so this isn't a global server outage — it's endpoint-specific.

**Note on locustfile parameter:** `benchmark/locustfile.py:198-204` calls `/orders/all-page?page=...&size=...`, but the Java controller (`java/.../controller/OrderController.java:52-72`) accepts `pageNumber`, `size`, `cursor`. The wrong param name (`page` vs `pageNumber`) may explain the 100% failure rate — the endpoint may be returning 400/500 because `pageNumber` is missing.

**Investigation steps:**
1. Confirm controller signature: `pageNumber` vs `page`. If `pageNumber`, the locustfile is wrong.
2. Inspect `single_20260422_235328_failures.csv` to see the exact HTTP status returned.
3. Check `single_20260422_235328_spring.log` for stack traces around `/orders/all-page` requests.

**Likely fix:** rename `page` → `pageNumber` in `benchmark/locustfile.py:198-204`. Same fix may be needed in the `wait_spring` and `validate_spring_data` curl calls in `benchmark/seed_and_run.sh:61,161,163` — those use `page=0&size=1` against the same endpoint and currently happen to work only if the controller defaults `pageNumber` to 0 when absent.

---

## Order of operations

1. Apply fix #1 (`down -v` in seed_and_run.sh) — unblocks re-seeding.
2. Investigate #3 first — it's small and may explain part of the noise across all four strategies.
3. Re-seed and re-run all four.
4. Investigate #2 if Citus still shows ~100% timeout after re-seed.
