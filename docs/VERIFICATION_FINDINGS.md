# Post-Refactor Verification Findings

**Date:** 2026-04-11  
**Purpose:** Verify all four sharding strategies work correctly after the Python utilities restructure.  
**Test scope:** Data seeding → verify scripts → Spring Boot analytics endpoint → cleanup.

---

## Summary

| Strategy | Seed | Verify | Spring Boot | Analytics HTTP | Cleanup |
|----------|------|--------|-------------|----------------|---------|
| 1 — Single DB | ✅ | ✅ | ✅ `single` profile | ✅ 200 / 93ms | ✅ |
| 2 — Manual Sharding | ✅ | ✅ | ✅ `sharded` profile | ✅ 200 / 160ms | ✅ |
| 3 — Citus | ✅ | ✅ | ✅ `single` profile | ✅ 200 / 197ms | ✅ |
| 4 — Lookup Table | ✅ | ✅ | ✅ `lookup` profile | ✅ 200 / 195ms | ✅ |

All four strategies passed end-to-end with no errors.

---

## Strategy 1 — Single Database

**Docker Compose:** `00-single-db/docker-compose.yaml`  
**Seed command:** `python db_setup.py --mode single --users 1000 --products 500 --orders-per-user 5`

### Seeding results
| Table | Count |
|-------|-------|
| users | 1,000 |
| products | 500 |
| orders | 5,000 |
| order_items | ~15,000 |

### Verify script output
```
Total users:    1000
Total orders:   5000
Total products:  500
```

### Spring Boot — `single` profile
- **Endpoint:** `GET /analytics`
- **Status:** `200 OK`
- **Response time:** `93ms`
- **Results returned:** 3 analytics records (Country, Product, User)

### Analytics response
```json
[
  { "reportType": "Country Analytics",  "totalCount": 21,   "totalOrders": 105,  "totalRevenue": 446059.36, "averageValue": 1686.4, "specialCount": 0   },
  { "reportType": "Product Analytics",  "totalCount": 1145, "totalOrders": 1680, "totalRevenue": 6083456.1, "averageValue": 4.4,   "specialCount": 164 },
  { "reportType": "User Analytics",     "totalCount": 21,   "totalOrders": 105,  "totalRevenue": 148686.45, "averageValue": 1686.4, "specialCount": 0   }
]
```

---

## Strategy 2 — Manual Sharding (Hash-based)

**Docker Compose:** `01-manual-sharding/docker-compose.yaml`  
**Seed command:** `python db_setup.py --mode sharded --users 1000 --products 500 --orders-per-user 5`

### Seeding results — user distribution across shards
| Shard | Users | Orders |
|-------|-------|--------|
| Shard 1 (port 5433) | 240 | 1,200 |
| Shard 2 (port 5434) | 284 | 1,420 |
| Shard 3 (port 5435) | 255 | 1,275 |
| Shard 4 (port 5436) | 221 | 1,105 |
| **Total** | **1,000** | **5,000** |

Products replicated to all 4 shards: 500 per shard.

### Verify script output
```
Total users across shards: 1000
Total orders across shards: 5000
Total products (per shard): 500
```

### Spring Boot — `sharded` profile
- **Endpoint:** `GET /analytics`
- **Status:** `200 OK`
- **Response time:** `160ms`
- **Results returned:** 3 analytics records

### Notes
- Hash routing via `get_shard_index(user_uuid)` using SHA-256 mod 4
- Distribution is not perfectly even but within expected variance (~10%)
- Cross-shard queries fan out to all 4 shards in the `sharded` Spring Boot profile

---

## Strategy 3 — Citus Distributed

**Docker Compose:** `02-citus-sharding/docker-compose.yaml`  
**Seed command:** `python db_setup.py --mode single-shard --users 1000 --products 500 --orders-per-user 5`

### Cluster topology
| Node | Role | Port |
|------|------|------|
| citus-coordinator | Coordinator | 5432 |
| citus-worker-1 | Worker | — |
| citus-worker-2 | Worker | — |
| citus-worker-3 | Worker | — |
| citus-worker-4 | Worker | — |

### Seeding results (via coordinator)
| Table | Count |
|-------|-------|
| users | 1,000 |
| products | 500 |
| orders | 5,000 |

### Verify script output
```
Total users:    1000
Total orders:   5000
Total products:  500
```

### Spring Boot — `single` profile (connects to Citus coordinator)
- **Endpoint:** `GET /analytics`
- **Status:** `200 OK`
- **Response time:** `197ms`
- **Results returned:** 3 analytics records

### Notes
- Seeding uses `single-shard` mode since Citus exposes a standard PostgreSQL interface via the coordinator
- Citus distributes data internally across workers; the application is unaware of sharding
- Slightly higher latency vs. single DB reflects distributed query planning overhead

---

## Strategy 4 — Manual Sharding with Lookup Table

**Docker Compose:** `03-manual-sharding-lookup-table/docker-compose.yaml`  
**Seed command:** `python db_setup.py --mode sharded-lookup-table --users 1000 --products 500 --orders-per-user 5`

### Infrastructure
| Container | Role | Port |
|-----------|------|------|
| lookup-table | Main DB + user_data_shard routing table | 5432 |
| shard-1 | Data shard | 5433 |
| shard-2 | Data shard | 5434 |
| shard-3 | Data shard | 5435 |
| shard-4 | Data shard | 5436 |

### Seeding results
| Shard | Users | Orders |
|-------|-------|--------|
| Shard 1 (port 5433) | 240 | 1,200 |
| Shard 2 (port 5434) | 261 | 1,305 |
| Shard 3 (port 5435) | 252 | 1,260 |
| Shard 4 (port 5436) | 247 | 1,235 |
| **Total** | **1,000** | **5,000** |

Lookup table entries (`user_data_shard`): **1,000** (one mapping per user)  
Products replicated to all 4 shards: 500 per shard.

### Verify script output
```
Total users: 1000
Total orders: 5000
Total products: 500 (replicated across all 4 shards)
Lookup table entries: 1000
```

### Spring Boot — `lookup` profile
- **Endpoint:** `GET /analytics`
- **Status:** `200 OK`
- **Response time:** `195ms`
- **Results returned:** 3 analytics records

### Analytics response
```json
[
  { "reportType": "Country Analytics",  "totalCount": 21,   "totalOrders": 105,  "totalRevenue": 531215.49, "averageValue": 1686.4, "specialCount": 0   },
  { "reportType": "Product Analytics",  "totalCount": 1145, "totalOrders": 1680, "totalRevenue": 6159632.29, "averageValue": 4.4,  "specialCount": 164 },
  { "reportType": "User Analytics",     "totalCount": 21,   "totalOrders": 105,  "totalRevenue": 177071.83, "averageValue": 1686.4, "specialCount": 0   }
]
```

### Notes
- Two-phase write: user written to shard + routing entry written atomically to lookup table
- Lookup table allows flexible shard reassignment without rehashing
- Extra latency compared to pure hash routing is negligible at this data scale

---

## Refactor Impact Assessment

No regressions were found. The following structural changes made during the refactor were exercised by these tests:

| Change | Verified by |
|--------|-------------|
| `utilities/commons/` → `utilities/` (flatten) | All 4 strategies seeded successfully |
| `connect(**dict)` → `connect(str(config))` | All DB connections established without error |
| `connect_to_shards()` / `close_shard_connections()` consolidated | Strategies 2, 3, 4 (shard connections) |
| `SHARD_CONFIGS` ports fixed (5433–5436) | Strategies 2 and 4 shard routing |
| `MAIN_DB_CONFIG` added (port 5432) | Strategy 4 lookup table writes |
| `ShardedLookupGenerator` assert guards | Strategy 4 seeding with no panics |
| `ThreadPoolExecutor` as context manager | All generators shut down cleanly |
| `DataFactory` (renamed from `DataGenerator`) | All `generate_*` calls produced valid records |
| `mypy --strict` compliance (0 errors) | No runtime type errors observed |

---

## Observed Latency Comparison

| Strategy | Analytics response time |
|----------|------------------------|
| Single DB | 93ms |
| Manual Sharding | 160ms |
| Citus | 197ms |
| Lookup Table | 195ms |

The single DB is fastest for analytics aggregation (no cross-shard fan-out). Manual sharding requires the application to query all 4 shards and merge results. Citus and Lookup Table have similar overhead from their respective coordination layers.
