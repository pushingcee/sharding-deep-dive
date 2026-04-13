# Database Sharding Exploration

A hands-on playground for exploring and confirming my understanding of sharding in a practical way. Inspired largely by DDIA's chapter on partitioning and Notion's blog article ["Herding Elephants"](https://www.notion.so/blog/sharding-postgres-at-notion).

The initial idea was to just implement what I'd read about. With time it grew.

## Long-term vision

- [x] Implement sharding: manual (hash-based) and via Citus
- [x] Compare both approaches to single instance performance in constrained Docker containers to make differences visible on smaller datasets
- [x] Add a lookup table sharding variant (shard routing via a central mapping table)
- [x] Load test all strategies with Locust under equal total resource budgets
- [ ] Implement a migration pipeline from a single PostgreSQL database to a Citus sharded database (Herding Elephants)

## Architecture approaches

### 1. Single Database (`00-single-db/`)
One PostgreSQL 16 instance on port 5432. The baseline.

### 2. Manual Sharding (`01-manual-sharding/`)
4 PostgreSQL instances (ports 5433–5436). Users are routed by `SHA-1(user_id.bytes) % 4`. Orders and order_items are co-located with their user. Products are replicated across all shards as a reference table. Routing happens at the application layer.

### 3. Citus (`02-citus-sharding/`)
Citus coordinator + 4 workers. Transparent to the application — connects to the coordinator like a regular PostgreSQL instance. Citus handles distribution and query planning internally.

### 4. Lookup Table Sharding (`03-manual-sharding-lookup-table/`)
Same 4-shard setup as manual sharding, but shard assignment is stored in a central `user_data_shard` table on a dedicated routing DB (port 5432). Slower to route but allows flexible shard reassignment without rehashing.

## Quick start

### Prerequisites
- Docker + Docker Compose
- Python 3.13+
- Java 21+ with Maven

### Setup
```bash
cd python
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Single database
```bash
cd 00-single-db && docker compose up -d
cd ../python && python db_setup.py --mode single --users 10000 --products 1000 --orders-per-user 5
cd ../java/e-commerce-simple-api && mvn spring-boot:run -Dspring-boot.run.profiles=single
```

### Manual sharding
```bash
cd 01-manual-sharding && docker compose up -d
cd ../python && python db_setup.py --mode sharded --users 10000 --products 1000 --orders-per-user 5
bash ../01-manual-sharding/verify-sharding.sh
cd ../java/e-commerce-simple-api && mvn spring-boot:run -Dspring-boot.run.profiles=sharded
```

### Citus
```bash
cd 02-citus-sharding
docker compose -f docker-compose-sharded-citus-refactored.yaml up -d
bash 01-disable-ssl.sh
docker compose -f docker-compose-sharded-citus-refactored.yaml restart
bash 02-set-workers-and-masters.sh
cd ../python && python db_setup.py --mode single-shard --users 10000 --products 1000 --orders-per-user 5
cd ../java/e-commerce-simple-api && mvn spring-boot:run -Dspring-boot.run.profiles=single
```

### Lookup table sharding
```bash
cd 03-manual-sharding-lookup-table && docker compose up -d
cd ../python && python db_setup.py --mode sharded-lookup-table --users 10000 --products 1000 --orders-per-user 5
bash ../03-manual-sharding-lookup-table/verify-sharding-lookup.sh
cd ../java/e-commerce-simple-api && mvn spring-boot:run -Dspring-boot.run.profiles=lookup
```

### Spring Boot profiles

Each strategy requires an explicit profile — omitting it causes a startup failure.

| Strategy | Profile flag |
|---|---|
| Single DB | `-Dspring-boot.run.profiles=single` |
| Manual Sharding | `-Dspring-boot.run.profiles=sharded` |
| Citus | `-Dspring-boot.run.profiles=single` |
| Lookup Table | `-Dspring-boot.run.profiles=lookup` |

### Test the API
```bash
curl http://localhost:8080/users/{user-id}
curl http://localhost:8080/orders/user/{user-id}
curl http://localhost:8080/analytics
```

## Load testing

Each strategy has a `docker-compose.benchmark.yaml` with constrained resources. All strategies get the same total budget (1 CPU / 512MB) split across their containers. The point is to answer whether architecture beats a single DB on equal hardware — not just "more hardware helps."

```bash
# Interactive mode — opens web UI at http://localhost:8089
cd benchmark && ./run_benchmark.sh

# Headless — 150 users, 15/s spawn, 3 minutes
./run_benchmark.sh single 150 15 180s
./run_benchmark.sh sharded 150 15 180s
./run_benchmark.sh citus 150 15 180s
./run_benchmark.sh lookup 150 15 180s
```

Three Locust user classes:
- `QuickReadUser` (weight 3) — user lookups, order queries
- `HeavyAnalyticsUser` (weight 1) — the `/analytics` endpoint, the key comparison point
- `MixedWorkloadUser` (weight 2) — realistic 10:1 read-to-analytics ratio

See `docs/VERIFICATION_FINDINGS.md` for post-refactor functional verification results.

## Consistent hashing

Python and Java implement identical sharding logic so a user inserted via the seed script is always found by the API:

```python
# Python
def get_shard_index(key_uuid: UUID, num_shards: int = 4) -> int:
    hash_digest = hashlib.sha1(key_uuid.bytes).digest()
    hash_int = int.from_bytes(hash_digest[:8], "big")
    return hash_int % num_shards
```

```java
// Java
public int getShardIndex(UUID userId) {
    byte[] uuidBytes = convertUuidToBytes(userId);
    byte[] hashDigest = sha1.digest(uuidBytes);
    long hashInt = convertBytesToLong(hashDigest);
    return (int) (hashInt % NUM_SHARDS);
}
```

## Key learnings

- **Serial keys are gone.** Moving to sharding forces UUIDs. You have to think carefully about what your sharding key is and whether related rows across tables end up on the same shard — if not, joins happen at the application layer.
- **Key selection is critical.** A poorly chosen key concentrates data on a single shard and defeats the purpose entirely.
- **The lookup table pattern exists for a reason.** Storing `(user_id, shard_id)` in a central table makes future shard migrations or reassignments far less painful than rehashing everything.
- **Citus is genuinely transparent.** The application connects to the coordinator exactly like a regular PostgreSQL instance. The tradeoff is the coordination overhead on every query.
- **Equal resources is a harder test than equal shards.** Giving all strategies the same total CPU/memory budget makes the benchmark meaningful — it tests architecture, not hardware.

## Project structure

```
├── 00-single-db/                         # Single PostgreSQL instance
├── 01-manual-sharding/                   # 4 PostgreSQL instances, app-level routing
├── 02-citus-sharding/                    # Citus coordinator + workers
├── 03-manual-sharding-lookup-table/      # 4 shards + central routing DB
├── benchmark/
│   ├── locustfile.py                     # Locust test scenarios
│   └── run_benchmark.sh                  # Benchmark runner
├── python/
│   ├── db_setup.py                       # CLI entry point
│   └── utilities/
│       ├── config.py                     # DbConfig
│       ├── constants.py                  # Shard configs, defaults
│       ├── connection_manager.py         # Connection pooling, shard helpers
│       ├── data_factory.py               # Faker-based data generation
│       ├── table_manager.py              # Schema creation per mode
│       ├── queries.py                    # DDL statements
│       ├── shard_utils.py                # get_shard_index, thread count
│       └── generators/
│           ├── base.py                   # BaseGenerator, generate_products_base
│           ├── single.py                 # SingleGenerator
│           ├── sharded.py                # ShardedGenerator
│           └── sharded_lookup.py         # ShardedLookupGenerator
├── java/e-commerce-simple-api/           # Spring Boot REST API
│   └── src/main/java/org/learn/
│       ├── configuration/                # DataSource configs per profile
│       ├── repository/                   # single/, sharded/, lookup/
│       ├── service/                      # Analytics, Order, User, Product
│       └── controller/
├── docs/
│   └── VERIFICATION_FINDINGS.md         # Post-refactor end-to-end test results
└── cleanup.sh                            # Stop containers and remove volumes
```

## Troubleshooting

```bash
# Check running containers
docker ps

# Check container logs
docker logs shard-1

# Enable debug logging on seed script
python db_setup.py --mode sharded --users 1000 --log-level DEBUG

# Full cleanup
./cleanup.sh
```
