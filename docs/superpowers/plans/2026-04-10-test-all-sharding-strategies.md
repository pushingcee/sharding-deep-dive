# Test All 4 Sharding Strategies - Execution Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Validate that all 4 database sharding strategies (single DB, manual sharding, Citus, lookup table) still work end-to-end: containers start, data generates, API serves queries, and benchmarks run.

**Architecture:** Each strategy runs independently. For each one: start Docker containers, generate fake data with Python, start the Spring Boot API with the correct profile, verify data via shell scripts, test API endpoints manually, and optionally run Locust benchmarks. Clean up between strategies to avoid port conflicts.

**Tech Stack:** Docker Compose, PostgreSQL 16, Citus 13, Python 3 (psycopg, Faker), Java 23 (Spring Boot 3.4.4, Maven), Locust (load testing)

---

## Prerequisites (One-Time Setup)

Before starting any strategy, ensure these are in place.

### Task 0: Environment Setup

**Files:** None created/modified

- [ ] **Step 1: Verify Docker is running**

```bash
docker info > /dev/null 2>&1 && echo "Docker OK" || echo "Docker not running - start it first"
```

Expected: `Docker OK`

- [ ] **Step 2: Verify Java 23+ is available**

```bash
java --version
```

Expected: Output shows java 23 or higher. If not, install via your package manager or SDKMAN (`sdk install java 23-open`).

- [ ] **Step 3: Verify Maven is available**

```bash
cd java/e-commerce-simple-api && mvn --version
```

Expected: Maven 3.x with Java 23.

- [ ] **Step 4: Set up Python virtual environment and install dependencies**

```bash
cd python
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Expected: Successfully installs `psycopg[binary]`, `psycopg-pool`, `Faker`, `locust`.

- [ ] **Step 5: Clean up any leftover containers from previous runs**

```bash
cd /home/denizn/Programming/SystemDesign/sharding_partitioning_postgres_claude
bash cleanup.sh
```

Expected: Stops/removes all project containers and volumes (errors for non-existing containers are fine).

---

## Strategy 1: Single Database

### Task 1: Start Single DB Containers

**Files:** `00-single-db/docker-compose.yaml`

- [ ] **Step 1: Start the single PostgreSQL container**

```bash
cd 00-single-db
docker compose up -d
```

Expected: Container `single_instance` starts on port **5432**.

- [ ] **Step 2: Wait for healthy status**

```bash
docker compose ps
```

Expected: `single_instance` shows status `healthy`. If `starting`, wait 10 seconds and retry.

- [ ] **Step 3: Test direct database connectivity**

```bash
docker exec -i single_instance psql -U postgres -d mydb -c "SELECT 1;"
```

Expected: Returns `1`.

### Task 2: Generate Fake Data (Single Mode)

**Files:** `python/db_setup.py`

- [ ] **Step 1: Run the data generator in single mode**

```bash
cd python
source venv/bin/activate
python db_setup.py --mode single --users 500 --products 200 --orders-per-user 3 --items-per-order 2
```

Expected: Logs show table creation, then user/product/order generation. Completes without errors. Use smaller counts (500 users) for a quick smoke test; scale up to 5000+ for benchmark testing.

- [ ] **Step 2: Verify data with the verify script**

```bash
cd 00-single-db
bash verify-single.sh
```

Expected: Output shows `Users: 500`, `Orders: ~1500`, `Products: 200`.

- [ ] **Step 3: Spot-check a query directly**

```bash
docker exec -i single_instance psql -U postgres -d mydb -c "SELECT user_id, first_name, email FROM users LIMIT 3;"
```

Expected: Returns 3 user rows with SERIAL integer IDs, names, and emails.

### Task 3: Start Spring Boot API (Default Profile)

**Files:** `java/e-commerce-simple-api/`

- [ ] **Step 1: Build and run the API with default (single) profile**

```bash
cd java/e-commerce-simple-api
mvn clean spring-boot:run
```

Expected: Application starts on port **8080**. Logs show Hibernate connecting to `localhost:5432/mydb`. Keep this running in a separate terminal.

- [ ] **Step 2: Test the health endpoint**

```bash
curl -s http://localhost:8080/actuator/health
```

Expected: `{"status":"UP"}` or similar Spring Boot health response.

- [ ] **Step 3: Fetch a user by ID**

First get a user_id:
```bash
docker exec -i single_instance psql -U postgres -d mydb -t -c "SELECT user_id FROM users LIMIT 1;"
```

Then query the API (replace `<USER_ID>` with the actual value):
```bash
curl -s http://localhost:8080/users/<USER_ID> | python3 -m json.tool
```

Expected: JSON with user details (first_name, last_name, email, country, etc.).

- [ ] **Step 4: Test the analytics endpoint**

```bash
curl -s -w "\nExecution time: %{header:X-Execution-Time-Ms}ms\n" http://localhost:8080/analytics | python3 -m json.tool
```

Expected: JSON array with 3 report types (`user_order_stats`, `product_performance`, `country_analytics`). Note the execution time for later comparison.

- [ ] **Step 5: Stop the API**

Press `Ctrl+C` in the terminal running Spring Boot.

### Task 4: Clean Up Single DB

- [ ] **Step 1: Tear down containers**

```bash
cd 00-single-db
docker compose down -v
```

Expected: Container stopped, volume removed.

---

## Strategy 2: Manual Sharding (4 Shards, Hash-Based)

### Task 5: Start Manual Sharding Containers

**Files:** `01-manual-sharding/docker-compose.yaml`

- [ ] **Step 1: Start the 4 shard containers + monitoring stack**

```bash
cd 01-manual-sharding
docker compose up -d
```

Expected: Containers `shard-1` through `shard-4` start on ports **5433-5436**. Monitoring containers (prometheus, grafana, exporters) also start.

- [ ] **Step 2: Wait for all shards to be healthy**

```bash
docker compose ps
```

Expected: All 4 shard containers show `healthy`. Monitoring containers should be `running`.

- [ ] **Step 3: Test connectivity to each shard**

```bash
for i in 1 2 3 4; do
  echo "Shard $i:"
  docker exec -i shard-$i psql -U postgres -d mydb -c "SELECT 1;"
done
```

Expected: Each shard returns `1`.

### Task 6: Generate Fake Data (Sharded Mode)

**Files:** `python/db_setup.py`

- [ ] **Step 1: Run the data generator in sharded mode**

```bash
cd python
source venv/bin/activate
python db_setup.py --mode sharded --users 500 --products 200 --orders-per-user 3 --items-per-order 2
```

Expected: Logs show users being distributed across 4 shards using SHA-1 hash routing. Products replicated to all shards. Completes without errors.

- [ ] **Step 2: Verify shard distribution**

```bash
cd 01-manual-sharding
bash verify-sharding.sh
```

Expected: Users roughly evenly distributed across 4 shards (~125 each). Orders distributed similarly. Products identical count on all 4 shards (200 each). Total users = 500, total orders ~1500.

- [ ] **Step 3: Confirm data co-location**

Pick a user from shard-1 and verify their orders are on the same shard:
```bash
USER_ID=$(docker exec -i shard-1 psql -U postgres -d mydb -t -c "SELECT user_id FROM users LIMIT 1;" | tr -d ' ')
echo "User ID: $USER_ID"
docker exec -i shard-1 psql -U postgres -d mydb -c "SELECT order_id, status FROM orders WHERE user_id = '$USER_ID';"
```

Expected: Returns orders for that user, proving co-location on the same shard.

### Task 7: Start Spring Boot API (Sharded Profile)

- [ ] **Step 1: Run the API with the sharded profile**

```bash
cd java/e-commerce-simple-api
mvn clean spring-boot:run -Dspring-boot.run.profiles=sharded
```

Expected: Application starts on port **8080**. Logs show 4 datasource connections being created (ports 5433-5436). Keep running in separate terminal.

- [ ] **Step 2: Fetch a user through the API**

Get a user_id from any shard:
```bash
USER_ID=$(docker exec -i shard-1 psql -U postgres -d mydb -t -c "SELECT user_id FROM users LIMIT 1;" | tr -d ' ')
curl -s http://localhost:8080/users/$USER_ID | python3 -m json.tool
```

Expected: API correctly routes to the right shard and returns user JSON.

- [ ] **Step 3: Fetch orders for that user**

```bash
curl -s http://localhost:8080/orders/user/$USER_ID | python3 -m json.tool
```

Expected: Returns a list of orders belonging to the user.

- [ ] **Step 4: Test cross-shard analytics**

```bash
curl -s -w "\nExecution time: %{header:X-Execution-Time-Ms}ms\n" http://localhost:8080/analytics | python3 -m json.tool
```

Expected: Aggregated analytics from all 4 shards. Compare execution time with single DB result.

- [ ] **Step 5: Check Grafana monitoring (optional)**

Open `http://localhost:3000` in a browser. Login: `admin` / `admin`.
Add Prometheus data source: `http://prometheus:9090`.
Verify you can see PostgreSQL metrics from the exporters.

- [ ] **Step 6: Stop the API**

Press `Ctrl+C` in the terminal running Spring Boot.

### Task 8: Clean Up Manual Sharding

- [ ] **Step 1: Tear down all containers and volumes**

```bash
cd 01-manual-sharding
docker compose down -v
```

Expected: All shard + monitoring containers stopped, volumes removed.

---

## Strategy 3: Citus Distributed Database

### Task 9: Start Citus Cluster

**Files:** `02-citus-sharding/docker-compose-sharded-citus-refactored.yaml`

- [ ] **Step 1: Start the Citus coordinator + 4 workers**

```bash
cd 02-citus-sharding
docker compose -f docker-compose-sharded-citus-refactored.yaml up -d
```

Expected: Containers `master` (port **5432**) and `worker-1` through `worker-4` start.

- [ ] **Step 2: Wait for all nodes to be healthy**

```bash
docker compose -f docker-compose-sharded-citus-refactored.yaml ps
```

Expected: All 5 containers show `healthy`.

- [ ] **Step 3: Disable SSL and configure the cluster**

```bash
bash 01-disable-ssl.sh
```

Then restart the containers so the SSL changes take effect:
```bash
docker compose -f docker-compose-sharded-citus-refactored.yaml restart
```

Wait for healthy again:
```bash
docker compose -f docker-compose-sharded-citus-refactored.yaml ps
```

- [ ] **Step 4: Set up coordinator and register workers**

```bash
bash 02-set-workers-and-masters.sh
```

Expected: Output shows workers being added. Final query `citus_get_active_worker_nodes()` lists all 4 workers. `pg_dist_node` shows coordinator + 4 workers.

- [ ] **Step 5: Verify Citus extension is active**

```bash
docker exec -i master psql -U postgres -d mydb -c "SELECT citus_version();"
```

Expected: Returns Citus version 13.x.

### Task 10: Generate Fake Data (Single Mode Against Citus Coordinator)

**Files:** `python/db_setup.py`

**Important:** Citus uses the coordinator (port 5432) as a single entry point. The Python generator uses `--mode single` because Citus handles distribution transparently. However, you need tables created with Citus distribution commands, not plain tables.

- [ ] **Step 1: Create distributed tables on the coordinator**

You need to create the tables first, then distribute them. Run against the coordinator:

```bash
docker exec -i master psql -U postgres -d mydb -c "
CREATE EXTENSION IF NOT EXISTS citus;

CREATE TABLE IF NOT EXISTS users (
    user_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    first_name VARCHAR(100) NOT NULL,
    last_name VARCHAR(100) NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    country CHAR(2) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    last_active DATE,
    preferences JSONB DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS products (
    product_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    description TEXT,
    price NUMERIC(10,2) NOT NULL,
    category VARCHAR(100),
    technical_specs JSONB DEFAULT '{}',
    search_vector TSVECTOR GENERATED ALWAYS AS (
        setweight(to_tsvector('english', coalesce(name, '')), 'A') ||
        setweight(to_tsvector('english', coalesce(description, '')), 'B')
    ) STORED
);

CREATE TABLE IF NOT EXISTS orders (
    order_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(user_id),
    order_date TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    total_amount DECIMAL(10, 2) NOT NULL,
    status VARCHAR(20) CHECK (status IN ('pending', 'shipped', 'delivered', 'cancelled'))
);

CREATE TABLE IF NOT EXISTS order_items (
    order_id UUID NOT NULL REFERENCES orders(order_id),
    product_id UUID NOT NULL REFERENCES products(product_id),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    PRIMARY KEY (order_id, product_id)
);

-- Distribute tables
SELECT create_distributed_table('users', 'user_id');
SELECT create_distributed_table('orders', 'user_id', colocate_with => 'users');
SELECT create_reference_table('products');
SELECT create_distributed_table('order_items', 'order_id', colocate_with => 'orders');
"
```

Expected: Tables created and distributed. Products is a reference table (replicated).

**Note:** If the `order_items` distribution fails due to foreign key constraints, drop the FK to products first or distribute without co-location. The exact Citus version may require adjustments.

- [ ] **Step 2: Generate data using the Python script in single mode**

```bash
cd python
source venv/bin/activate
python db_setup.py --mode single --users 500 --products 200 --orders-per-user 3 --items-per-order 2 --skip-creation
```

Note: `--skip-creation` because we already created the tables with Citus distribution. The `single` mode talks to port 5432 (the coordinator), and Citus handles sharding transparently.

Expected: Data generation completes. Citus distributes rows to workers automatically.

- [ ] **Step 3: Verify data through the coordinator**

```bash
cd 02-citus-sharding
bash verify-citus.sh
```

Expected: Shows total Users: 500, Orders: ~1500, Products: 200 across the distributed cluster.

- [ ] **Step 4: Verify data is actually distributed across workers**

```bash
docker exec -i master psql -U postgres -d mydb -c "
SELECT nodename, count(*) 
FROM citus_shards 
JOIN pg_dist_placement USING (shardid)
JOIN pg_dist_node ON (groupid = pg_dist_node.groupid)
WHERE table_name::text = 'users'
GROUP BY nodename;
"
```

Expected: Shows shard counts distributed across worker-1 through worker-4.

### Task 11: Start Spring Boot API (Default Profile for Citus)

- [ ] **Step 1: Run the API with default profile (connects to port 5432 = coordinator)**

```bash
cd java/e-commerce-simple-api
mvn clean spring-boot:run
```

Expected: Starts on port **8080**, connecting to Citus coordinator at localhost:5432. The app doesn't know it's Citus - it looks like a single database.

- [ ] **Step 2: Test a user query**

```bash
USER_ID=$(docker exec -i master psql -U postgres -d mydb -t -c "SELECT user_id FROM users LIMIT 1;" | tr -d ' ')
curl -s http://localhost:8080/users/$USER_ID | python3 -m json.tool
```

Expected: Returns user JSON. Citus routes the query to the correct worker transparently.

- [ ] **Step 3: Test analytics**

```bash
curl -s -w "\nExecution time: %{header:X-Execution-Time-Ms}ms\n" http://localhost:8080/analytics | python3 -m json.tool
```

Expected: Analytics results. Citus pushes computation down to workers and aggregates. Compare time with previous strategies.

- [ ] **Step 4: Stop the API**

Press `Ctrl+C`.

### Task 12: Clean Up Citus

- [ ] **Step 1: Tear down the cluster**

```bash
cd 02-citus-sharding
docker compose -f docker-compose-sharded-citus-refactored.yaml down -v
```

Expected: All Citus containers and volumes removed.

---

## Strategy 4: Lookup Table Sharding

### Task 13: Start Lookup Table Containers

**Files:** `03-manual-sharding-lookup-table/docker-compose.yaml`

- [ ] **Step 1: Start the lookup DB + 4 shards**

```bash
cd 03-manual-sharding-lookup-table
docker compose up -d
```

Expected: Container `lookup-table` on port **5432** (central routing DB) and `shard-1` through `shard-4` on ports **5433-5436**.

- [ ] **Step 2: Wait for healthy status**

```bash
docker compose ps
```

Expected: All 5 containers show `healthy`.

- [ ] **Step 3: Test connectivity**

```bash
docker exec -i lookup-table psql -U postgres -d mydb -c "SELECT 1;"
for i in 1 2 3 4; do
  echo "Shard $i:"
  docker exec -i shard-$i psql -U postgres -d mydb -c "SELECT 1;"
done
```

Expected: All return `1`.

### Task 14: Generate Fake Data (Lookup Table Mode)

- [ ] **Step 1: Run the data generator in sharded-lookup-table mode**

```bash
cd python
source venv/bin/activate
python db_setup.py --mode sharded-lookup-table --users 500 --products 200 --orders-per-user 3 --items-per-order 2
```

Expected: Creates tables on all shards + lookup table on central DB. Generates users, inserts into shards, and records user_id -> shard_id mappings in the lookup table.

- [ ] **Step 2: Verify shard distribution and lookup table**

```bash
cd 03-manual-sharding-lookup-table
bash verify-sharding-lookup.sh
```

Expected: Users distributed across 4 shards (~125 each). Orders distributed similarly. Products replicated (200 each). **Lookup table entries: 500** (one mapping per user).

- [ ] **Step 3: Verify lookup table content**

```bash
docker exec -i lookup-table psql -U postgres -d mydb -c "SELECT * FROM user_data_shard LIMIT 5;"
```

Expected: Shows rows with `user_id` (UUID) and `shard_id` (1-4).

- [ ] **Step 4: Cross-reference a lookup entry with actual shard data**

```bash
# Get a user and their shard from the lookup table
docker exec -i lookup-table psql -U postgres -d mydb -t -c "SELECT user_id, shard_id FROM user_data_shard LIMIT 1;"
```

Take the user_id and shard_id from the output, then verify the user exists on that shard:
```bash
# Replace <USER_ID> and <SHARD_NUM> with actual values
docker exec -i shard-<SHARD_NUM> psql -U postgres -d mydb -c "SELECT first_name, email FROM users WHERE user_id = '<USER_ID>';"
```

Expected: User found on the shard indicated by the lookup table.

### Task 15: Start Spring Boot API (Lookup Profile)

- [ ] **Step 1: Run the API with the lookup profile**

```bash
cd java/e-commerce-simple-api
mvn clean spring-boot:run -Dspring-boot.run.profiles=lookup
```

Expected: Starts on port **8080**. Logs show connections to lookup DB (5432) + 4 shard DBs (5433-5436). Keep running.

- [ ] **Step 2: Test user fetch (lookup-routed)**

```bash
USER_ID=$(docker exec -i lookup-table psql -U postgres -d mydb -t -c "SELECT user_id FROM user_data_shard LIMIT 1;" | tr -d ' ')
curl -s http://localhost:8080/users/$USER_ID | python3 -m json.tool
```

Expected: API queries the lookup table to find the shard, then fetches the user. Returns user JSON.

- [ ] **Step 3: Test orders fetch**

```bash
curl -s http://localhost:8080/orders/user/$USER_ID | python3 -m json.tool
```

Expected: Returns orders for that user.

- [ ] **Step 4: Test analytics**

```bash
curl -s -w "\nExecution time: %{header:X-Execution-Time-Ms}ms\n" http://localhost:8080/analytics | python3 -m json.tool
```

Expected: Aggregated analytics from all shards. Note execution time.

- [ ] **Step 5: Stop the API**

Press `Ctrl+C`.

### Task 16: Clean Up Lookup Table

- [ ] **Step 1: Tear down containers**

```bash
cd 03-manual-sharding-lookup-table
docker compose down -v
```

Expected: All containers and volumes removed.

---

## Strategy Comparison (Optional - Benchmarking)

### Task 17: Run Locust Benchmarks

This task is optional but recommended if you want to compare performance across strategies. For each strategy, you need to:
1. Have the DB containers running
2. Generate a larger dataset (5000+ users)
3. Have the Spring Boot API running with the correct profile
4. Run the benchmark

- [ ] **Step 1: Pick a strategy to benchmark (repeat for each)**

Start the DB for the strategy you want to test (follow the relevant Task above), then generate a larger dataset:

```bash
cd python
source venv/bin/activate
# For single:
python db_setup.py --mode single --users 5000 --products 500 --orders-per-user 5 --items-per-order 3
# For sharded:
python db_setup.py --mode sharded --users 5000 --products 500 --orders-per-user 5 --items-per-order 3
# For lookup:
python db_setup.py --mode sharded-lookup-table --users 5000 --products 500 --orders-per-user 5 --items-per-order 3
# For Citus: use --mode single --skip-creation (after creating distributed tables)
```

- [ ] **Step 2: Start the API with the matching profile**

```bash
cd java/e-commerce-simple-api
# Single/Citus (default profile):
mvn clean spring-boot:run
# Manual sharding:
mvn clean spring-boot:run -Dspring-boot.run.profiles=sharded
# Lookup table:
mvn clean spring-boot:run -Dspring-boot.run.profiles=lookup
```

- [ ] **Step 3: Run the benchmark (headless)**

```bash
cd benchmark
bash run_benchmark.sh single 50 10 60s
# Or: bash run_benchmark.sh sharded 50 10 60s
# Or: bash run_benchmark.sh citus 50 10 60s
# Or: bash run_benchmark.sh lookup 50 10 60s
```

Expected: Locust runs for 60 seconds with 50 users. Results saved to `benchmark/results/`.

- [ ] **Step 4: Run interactive mode (optional)**

```bash
cd benchmark
bash run_benchmark.sh
```

Open `http://localhost:8089` in your browser. Configure users/spawn rate manually and watch real-time graphs.

- [ ] **Step 5: Compare results**

Open the HTML reports in `benchmark/results/`:
```bash
ls -lt benchmark/results/*.html
```

Key metrics to compare:
- **p50/p95/p99 response times** for `/users/{uuid}` (single-shard reads)
- **p50/p95/p99 response times** for `/analytics` (cross-shard heavy queries)
- **Requests per second** (throughput)
- **Failure rate**

---

## Troubleshooting Reference

### Common Issues

| Problem | Cause | Fix |
|---------|-------|-----|
| Port 5432 already in use | Previous strategy not cleaned up | Run `bash cleanup.sh` from project root |
| Python `ModuleNotFoundError` | Virtual env not activated | `source python/venv/bin/activate` |
| Java compilation fails | Wrong Java version | Ensure Java 23+ with `java --version` |
| Citus workers not connecting | SSL not disabled | Run `01-disable-ssl.sh`, restart, then `02-set-workers-and-masters.sh` |
| API returns 500 for user query | User routed to wrong shard | Verify hash algorithm consistency between Python and Java |
| `pg_isready` fails | Container still starting | Wait 15 seconds, check `docker compose ps` |
| Benchmark shows 100% failures | API not running | Start Spring Boot first |
| Data generation hangs | DB not ready | Check container health first |

### Port Map Quick Reference

| Strategy | Component | Port |
|----------|-----------|------|
| Single | PostgreSQL | 5432 |
| Manual Sharding | Shard 1-4 | 5433-5436 |
| Manual Sharding | Prometheus | 9090 |
| Manual Sharding | Grafana | 3000 |
| Citus | Coordinator | 5432 |
| Lookup Table | Lookup DB | 5432 |
| Lookup Table | Shard 1-4 | 5433-5436 |
| All | Spring Boot API | 8080 |
| Benchmark | Locust Web UI | 8089 |
