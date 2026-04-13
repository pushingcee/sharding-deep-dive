# Database Sharding Benchmark

Load testing suite using [Locust](https://locust.io/) to compare performance across different database sharding strategies.

## Quick Start

```bash
# 1. Install dependencies
cd python
pip install -r requirements.txt

# 2. Start database (choose one strategy)
cd ../00-single-db
docker-compose -f docker-compose.benchmark.yaml up -d

# 3. Start the Spring Boot API
cd ../java/e-commerce-simple-api
mvn spring-boot:run

# 4. Run benchmark (interactive mode)
cd ../../benchmark
./run_benchmark.sh
# Open http://localhost:8089

# 5. Or run headless benchmark
./run_benchmark.sh single 50 10 60s
```

## Test Scenarios

### QuickReadUser (weight: 3)
Simulates typical read operations:
- `GET /users/{uuid}` - User profile lookup
- `GET /orders/{uuid}` - Order details
- `GET /orders/user/{uuid}` - User's order history
- `GET /orders/all-page` - Paginated order listing

### HeavyAnalyticsUser (weight: 1)
Runs complex cross-shard analytics:
- `GET /analytics` - Heavy query with JOINs, CTEs, aggregations

**This is the key endpoint for comparing sharding benefits.**

### MixedWorkloadUser (weight: 2)
Realistic production workload:
- 90% quick reads
- 10% analytics queries

## Comparing Strategies

Run the same benchmark against each database configuration:

```bash
# 1. Single Database
cd 00-single-db
docker-compose -f docker-compose.benchmark.yaml up -d
# Start API, run benchmark, save results

# 2. Manual Sharding
cd ../01-manual-sharding
docker-compose -f docker-compose.benchmark.yaml up -d
# Start API with: mvn spring-boot:run -Dspring-boot.run.profiles=sharded

# 3. Citus
cd ../02-citus-sharding
docker-compose -f docker-compose.benchmark.yaml up -d

# 4. Lookup Table Sharding
cd ../03-manual-sharding-lookup-table
docker-compose -f docker-compose.benchmark.yaml up -d
# Start API with: mvn spring-boot:run -Dspring-boot.run.profiles=lookup
```

## Results

Results are saved to `benchmark/results/`:
- `*.html` - Visual HTML report
- `*_stats.csv` - Request statistics
- `*_stats_history.csv` - Time series data
- `*.log` - Console output

## Key Metrics to Compare

| Metric | What it shows |
|--------|---------------|
| **p50 Response Time** | Typical user experience |
| **p95 Response Time** | Tail latency |
| **p99 Response Time** | Worst-case scenarios |
| **Requests/sec** | Throughput capacity |
| **Failure Rate** | System stability under load |

## Expected Results

With constrained resources (0.5 CPU, 256MB total):

- **Single DB**: Higher latency as load increases (bottleneck)
- **Manual Sharding**: Lower latency due to parallel query execution
- **Citus**: Similar to manual sharding, with simpler query routing
- **Lookup Table**: Slightly higher latency than hash-based due to routing overhead

## Tips

1. **Warm up the database** before benchmarking:
   ```bash
   ./run_benchmark.sh single 10 5 30s  # Light warm-up
   ```

2. **Use consistent test parameters** across strategies for fair comparison

3. **Monitor container resources** during tests:
   ```bash
   docker stats
   ```

4. **Check the X-Execution-Time-Ms header** in responses for server-side timing
