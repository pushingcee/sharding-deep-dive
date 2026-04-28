#!/bin/bash
# Benchmark all 4 sharding strategies (or a single one via --only).
# Assumes volumes are already seeded. Pass --seed to seed volumes first.
#
# Usage:
#   ./seed_and_run.sh                         # benchmark all 4 (volumes must exist)
#   ./seed_and_run.sh --seed                  # seed all 4, then benchmark all 4
#   ./seed_and_run.sh --only lookup           # benchmark only lookup
#   ./seed_and_run.sh --seed --only lookup    # seed lookup, then benchmark lookup
#   STRATEGY: single | sharded | citus | lookup

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
JAVA_DIR="$PROJECT_ROOT/java/e-commerce-simple-api"
PYTHON_DIR="$PROJECT_ROOT/python"
PYTHON_VENV="$PYTHON_DIR/venv"
BENCH_VENV="$SCRIPT_DIR/.venv"
RESULTS_DIR="$SCRIPT_DIR/results"
ENV_FILE="${BENCHMARK_ENV_FILE:-$PROJECT_ROOT/benchmark-controls.env}"

USERS_SINGLE="${USERS_SINGLE:-1000000}"
USERS_MULTI="${USERS_MULTI:-1000000}"
BENCH_USERS="${BENCH_USERS:-40}"
BENCH_SPAWN="${BENCH_SPAWN:-2}"
BENCH_DURATION="${BENCH_DURATION:-120s}"

# Parse flags: --seed, --only STRATEGY
DO_SEED=0
ONLY=""
while [ $# -gt 0 ]; do
  case "$1" in
    --seed) DO_SEED=1; shift ;;
    --only)
      ONLY="$2"; shift 2
      case "$ONLY" in
        single|sharded|citus|lookup) ;;
        *) echo "ERR: --only must be one of: single, sharded, citus, lookup" >&2; exit 1 ;;
      esac
      ;;
    --help|-h) sed -n '2,11p' "$0"; exit 0 ;;
    *) echo "ERR: unknown arg: $1" >&2; exit 1 ;;
  esac
done

run_strategy() { [ -z "$ONLY" ] || [ "$ONLY" = "$1" ]; }

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; BLUE='\033[0;34m'; NC='\033[0m'
log()     { echo -e "${GREEN}[$(date +%H:%M:%S)]${NC} $1"; }
warn()    { echo -e "${YELLOW}[$(date +%H:%M:%S)] WARN:${NC} $1"; }
err()     { echo -e "${RED}[$(date +%H:%M:%S)] ERR:${NC} $1"; }
section() {
  echo ""
  echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
  echo -e "${BLUE}  $1${NC}"
  echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
  echo ""
}

mkdir -p "$RESULTS_DIR"

# ── helpers ───────────────────────────────────────────────────────────────────

dc() { docker compose --env-file "$ENV_FILE" "$@"; }

kill_spring() {
  pkill -f "spring-boot:run" 2>/dev/null || true
  pkill -f "e-commerce-simple-api" 2>/dev/null || true
  sleep 2
}

wait_spring() {
  local max=180 elapsed=0 code
  log "Waiting for Spring Boot..."
  while [ $elapsed -lt $max ]; do
    # curl -w "%{http_code}" always prints a 3-char code; "000" on connection refused.
    code=$(curl -s --connect-timeout 3 --max-time 5 -o /dev/null \
      -w "%{http_code}" "http://localhost:8080/orders/all-page?page=0&size=1" 2>/dev/null) || code="000"
    if [[ "$code" =~ ^[1-9][0-9]{2}$ ]]; then
      log "Spring Boot ready (HTTP $code)."
      return 0
    fi
    sleep 3; elapsed=$((elapsed+3)); printf "."
  done
  echo ""
  err "Spring Boot did not start within ${max}s"
  return 1
}

wait_healthy() {
  local compose_file="$1" max=120 elapsed=0
  log "Waiting for containers to become healthy..."
  while [ $elapsed -lt $max ]; do
    local not_ready
    not_ready=$(dc -f "$compose_file" ps --format json 2>/dev/null \
      | python3 -c "
import sys, json
lines = sys.stdin.read().strip()
not_ready = 0
for line in lines.splitlines():
    if not line.strip(): continue
    try:
        s = json.loads(line)
        h = s.get('Health','')
        if h and h != 'healthy':
            not_ready += 1
    except: pass
print(not_ready)
" 2>/dev/null || echo "0")
    if [ "$not_ready" = "0" ]; then
      log "Containers healthy."
      return 0
    fi
    sleep 5; elapsed=$((elapsed+5)); printf "."
  done
  echo ""
  warn "Timeout waiting for health — proceeding anyway."
}

start_spring() {
  local strategy="$1"
  local profile="$2"
  local ts="$3"
  local log_path="$RESULTS_DIR/${strategy}_${ts}_spring.log"
  log "Spring log → $log_path"
  cd "$JAVA_DIR"
  SPRING_PROFILES_ACTIVE="$profile" mvn spring-boot:run \
    -Dspring-boot.run.profiles="$profile" -q \
    > "$log_path" 2>&1 &
  SPRING_PID=$!
}

# Run in subshell so cd inside doesn't affect parent CWD
seed_db() {
  local mode="$1"
  local users="$3"
  log "Seeding DB mode=$mode from CSV (users=$users)..."
  (
    cd "$PYTHON_DIR"
    source "$PYTHON_VENV/bin/activate"
    python db_setup.py --mode "$mode" --use-csv-seed --users "$3"
  )
  log "Seeding complete."
}

LAST_LOCUST_OUT=""

run_locust() {
  local label="$1"
  local ts="${2:-$(date +%Y%m%d_%H%M%S)}"
  local out="$RESULTS_DIR/${label}_${ts}"
  LAST_LOCUST_OUT="$out"
  log "Running Locust → ${out}_stats.csv"
  "$BENCH_VENV/bin/locust" \
    -f "$SCRIPT_DIR/locustfile.py" \
    --host="http://localhost:8080" \
    --users "$BENCH_USERS" \
    --spawn-rate "$BENCH_SPAWN" \
    --run-time "$BENCH_DURATION" \
    --headless \
    --csv="$out" \
    --html="${out}.html" \
    2>&1 | tee "${out}.log"
  log "Done: ${out}_stats.csv"
}

citus_configure() {
  log "Configuring Citus cluster..."
  sleep 5
  docker exec master psql -U postgres -d mydb -c "ALTER SYSTEM SET citus.node_conninfo = 'sslmode=disable';" 2>/dev/null || true
  docker exec master psql -U postgres -d mydb -c "SELECT pg_reload_conf();" 2>/dev/null || true
  for i in 1 2 3 4; do
    docker exec "worker-$i" psql -U postgres -d mydb -c "ALTER SYSTEM SET citus.node_conninfo = 'sslmode=disable';" 2>/dev/null || true
    docker exec "worker-$i" psql -U postgres -d mydb -c "SELECT pg_reload_conf();" 2>/dev/null || true
  done
  docker exec master psql -U postgres -d mydb -c "SELECT citus_set_coordinator_host('master', 5432);" 2>/dev/null || true
  for i in 1 2 3 4; do
    docker exec master psql -U postgres -d mydb -c "SELECT citus_add_node('worker-$i', 5432);" 2>/dev/null || true
  done
  log "Citus cluster configured."
}

# Validate that /orders/all-page returns real data before running Locust.
# If this fails the Locust SAMPLE_USER_IDS list will be empty → all user/order
# lookups hit the hard-coded invalid UUID → 100% 404s → useless results.
validate_spring_data() {
  log "Pre-Locust check: /orders/all-page?page=0&size=10 ..."
  local i
  for i in 1 2 3 4 5; do
    local http_code body
    body=$(curl -sf --connect-timeout 5 "http://localhost:8080/orders/all-page?page=0&size=10" 2>/dev/null)
    http_code=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 5 \
      "http://localhost:8080/orders/all-page?page=0&size=10" 2>/dev/null)

    if [ "$http_code" = "200" ]; then
      local count
      count=$(echo "$body" | python3 -c \
        "import sys,json; d=json.load(sys.stdin); c=d.get('content',[]); print(len(c))" 2>/dev/null || echo "0")
      if [ "$count" -gt 0 ]; then
        log "Validation passed: /orders/all-page returned $count orders (HTTP 200). Locust IDs will populate."
        return 0
      else
        warn "Attempt $i: HTTP 200 but 0 orders in content. Retrying in 5s..."
      fi
    else
      warn "Attempt $i: /orders/all-page returned HTTP $http_code. Retrying in 5s..."
    fi
    sleep 5
  done

  err "╔══════════════════════════════════════════════════════════════╗"
  err "║  LOCUST INIT CHECK FAILED — stopping before benchmark run.  ║"
  err "║  /orders/all-page is not returning data after 5 attempts.   ║"
  err "║  Possible causes:                                            ║"
  err "║    - DB seeding did not complete successfully                ║"
  err "║    - Spring Boot connected to the wrong/empty database       ║"
  err "║    - orders table is empty                                   ║"
  err "║  Action: check 'docker compose ps', Spring logs above, then  ║"
  err "║          re-run with SKIP_SEED_*=1 if data is intact.       ║"
  err "╚══════════════════════════════════════════════════════════════╝"
  return 1
}

# After Locust finishes, inspect the failures CSV.
# If /users/{uuid} or /orders/{uuid} have >20 404 errors it almost certainly
# means SAMPLE_USER_IDS was empty (Locust used the hardcoded invalid UUID).
check_locust_results() {
  local csv_base="$1"
  local failures_csv="${csv_base}_failures.csv"
  local stats_csv="${csv_base}_stats.csv"

  if [ ! -f "$failures_csv" ]; then
    log "No failures CSV found — treating as clean run."
    return 0
  fi

  local user_404 order_404
  user_404=$(grep "/users/{uuid}" "$failures_csv" | grep "404" | \
    python3 -c "import sys; print(sum(int(l.strip().split(',')[-1]) for l in sys.stdin if l.strip()))" 2>/dev/null || echo "0")
  order_404=$(grep "/orders/{uuid}" "$failures_csv" | grep "404" | \
    python3 -c "import sys; print(sum(int(l.strip().split(',')[-1]) for l in sys.stdin if l.strip()))" 2>/dev/null || echo "0")

  if [ "${user_404:-0}" -gt 500 ] || [ "${order_404:-0}" -gt 500 ]; then
    err "╔══════════════════════════════════════════════════════════════╗"
    err "║  SUSPICIOUS RESULTS DETECTED — stopping pipeline.           ║"
    err "║  /users/{uuid}  → ${user_404} × 404 errors                          ║"
    err "║  /orders/{uuid} → ${order_404} × 404 errors                         ║"
    err "║  This strongly suggests SAMPLE_USER_IDS was empty           ║"
    err "║  (Locust init request failed during test start).            ║"
    err "║  Results at ${stats_csv} are INVALID.          ║"
    err "║  Action required — pipeline paused. Check logs and retry.   ║"
    err "╚══════════════════════════════════════════════════════════════╝"
    return 1
  fi

  log "Result check passed: user_404=$user_404, order_404=$order_404"
  return 0
}

# ── Strategy 1: Single DB ─────────────────────────────────────────────────────

if run_strategy single; then
  SINGLE_COMPOSE="$PROJECT_ROOT/00-single-db/docker-compose.yaml"
  SINGLE_BENCH_COMPOSE="$PROJECT_ROOT/00-single-db/docker-compose.benchmark.yaml"

  section "1/4  Single DB"
  if [ "$DO_SEED" = "1" ]; then
    dc -f "$SINGLE_COMPOSE" up -d
    wait_healthy "$SINGLE_COMPOSE"
    seed_db "single" "" "$USERS_SINGLE"
    dc -f "$SINGLE_COMPOSE" down
    log "Single DB seeded."
  else
    log "Skipping seed (run with --seed to populate volumes)"
  fi

  TS=$(date +%Y%m%d_%H%M%S)
  dc -f "$SINGLE_BENCH_COMPOSE" up -d
  wait_healthy "$SINGLE_BENCH_COMPOSE"

  kill_spring
  start_spring "single" "single" "$TS"
  wait_spring
  sleep 30  # allow pool to warm up before validation

  validate_spring_data || { kill $SPRING_PID 2>/dev/null || true; kill_spring; dc -f "$SINGLE_BENCH_COMPOSE" down; exit 1; }

  run_locust "single" "$TS"
  check_locust_results "$LAST_LOCUST_OUT" || { kill $SPRING_PID 2>/dev/null || true; kill_spring; dc -f "$SINGLE_BENCH_COMPOSE" down; exit 1; }

  kill $SPRING_PID 2>/dev/null || true; kill_spring
  dc -f "$SINGLE_BENCH_COMPOSE" down
  log "Single DB done."
fi

# ── Strategy 2: Manual Sharding ───────────────────────────────────────────────

if run_strategy sharded; then
  SHARDED_COMPOSE="$PROJECT_ROOT/01-manual-sharding/docker-compose.yaml"
  SHARDED_BENCH_COMPOSE="$PROJECT_ROOT/01-manual-sharding/docker-compose.benchmark.yaml"

  section "2/4  Manual Sharding"
  if [ "$DO_SEED" = "1" ]; then
    dc -f "$SHARDED_COMPOSE" up -d
    wait_healthy "$SHARDED_COMPOSE"
    seed_db "sharded" "" "$USERS_MULTI"
    dc -f "$SHARDED_COMPOSE" down
    log "Manual Sharding seeded."
  else
    log "Skipping seed (run with --seed to populate volumes)"
  fi

  TS=$(date +%Y%m%d_%H%M%S)
  dc -f "$SHARDED_BENCH_COMPOSE" up -d
  wait_healthy "$SHARDED_BENCH_COMPOSE"

  kill_spring
  start_spring "sharded" "sharded" "$TS"
  wait_spring
  sleep 5

  validate_spring_data || { kill $SPRING_PID 2>/dev/null || true; kill_spring; dc -f "$SHARDED_BENCH_COMPOSE" down; exit 1; }

  run_locust "sharded" "$TS"
  check_locust_results "$LAST_LOCUST_OUT" || { kill $SPRING_PID 2>/dev/null || true; kill_spring; dc -f "$SHARDED_BENCH_COMPOSE" down; exit 1; }

  kill $SPRING_PID 2>/dev/null || true; kill_spring
  dc -f "$SHARDED_BENCH_COMPOSE" down
  log "Manual Sharding done."
fi

# ── Strategy 3: Citus ─────────────────────────────────────────────────────────

if run_strategy citus; then
  CITUS_SEED_COMPOSE="$PROJECT_ROOT/02-citus-sharding/docker-compose-sharded-citus.yaml"
  CITUS_BENCH_COMPOSE="$PROJECT_ROOT/02-citus-sharding/docker-compose.benchmark.yaml"

  section "3/4  Citus"
  if [ "$DO_SEED" = "1" ]; then
    dc -f "$CITUS_SEED_COMPOSE" up -d
    wait_healthy "$CITUS_SEED_COMPOSE"
    citus_configure
    seed_db "single-shard" "" "$USERS_MULTI"
    dc -f "$CITUS_SEED_COMPOSE" down
    log "Citus seeded."
  else
    log "Skipping seed (run with --seed to populate volumes)"
  fi

  TS=$(date +%Y%m%d_%H%M%S)
  dc -f "$CITUS_BENCH_COMPOSE" up -d
  wait_healthy "$CITUS_BENCH_COMPOSE"
  citus_configure   # re-register after container restart

  kill_spring
  start_spring "citus" "single" "$TS"
  wait_spring
  sleep 5

  validate_spring_data || { kill $SPRING_PID 2>/dev/null || true; kill_spring; dc -f "$CITUS_BENCH_COMPOSE" down; exit 1; }

  run_locust "citus" "$TS"
  check_locust_results "$LAST_LOCUST_OUT" || { kill $SPRING_PID 2>/dev/null || true; kill_spring; dc -f "$CITUS_BENCH_COMPOSE" down; exit 1; }

  kill $SPRING_PID 2>/dev/null || true; kill_spring
  dc -f "$CITUS_BENCH_COMPOSE" down
  log "Citus done."
fi

# ── Strategy 4: Lookup Table ──────────────────────────────────────────────────

if run_strategy lookup; then
  LOOKUP_COMPOSE="$PROJECT_ROOT/03-manual-sharding-lookup-table/docker-compose.yaml"
  LOOKUP_BENCH_COMPOSE="$PROJECT_ROOT/03-manual-sharding-lookup-table/docker-compose.benchmark.yaml"

  section "4/4  Lookup Table"
  if [ "$DO_SEED" = "1" ]; then
    dc -f "$LOOKUP_COMPOSE" up -d
    wait_healthy "$LOOKUP_COMPOSE"
    seed_db "sharded-lookup-table" "" "$USERS_MULTI"
    dc -f "$LOOKUP_COMPOSE" down
    log "Lookup Table seeded."
  else
    log "Skipping seed (run with --seed to populate volumes)"
  fi

  TS=$(date +%Y%m%d_%H%M%S)
  dc -f "$LOOKUP_BENCH_COMPOSE" up -d
  wait_healthy "$LOOKUP_BENCH_COMPOSE"

  kill_spring
  start_spring "lookup" "lookup" "$TS"
  wait_spring
  sleep 5

  validate_spring_data || { kill $SPRING_PID 2>/dev/null || true; kill_spring; dc -f "$LOOKUP_BENCH_COMPOSE" down; exit 1; }

  run_locust "lookup" "$TS"
  check_locust_results "$LAST_LOCUST_OUT" || { kill $SPRING_PID 2>/dev/null || true; kill_spring; dc -f "$LOOKUP_BENCH_COMPOSE" down; exit 1; }

  kill $SPRING_PID 2>/dev/null || true; kill_spring
  dc -f "$LOOKUP_BENCH_COMPOSE" down
  log "Lookup Table done."
fi

# ── Summary ───────────────────────────────────────────────────────────────────

section "All benchmarks complete"
log "Results in $RESULTS_DIR:"
ls -lt "$RESULTS_DIR"/*_stats.csv 2>/dev/null | head -8
