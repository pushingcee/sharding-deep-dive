#!/bin/bash
# Run benchmarks against existing seeded volumes.
# Does NOT clean up or re-seed — volumes must already have data.
#
# Usage:
#   ./run_benchmarks_existing_data.sh [--only STRATEGY] [BENCH_USERS] [BENCH_SPAWN] [BENCH_DURATION]
#   STRATEGY: single | sharded | citus | lookup
# Examples:
#   ./run_benchmarks_existing_data.sh                      # all 4
#   ./run_benchmarks_existing_data.sh --only lookup        # lookup only
#   ./run_benchmarks_existing_data.sh --only sharded 60 5 120s

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
JAVA_DIR="$PROJECT_ROOT/java/e-commerce-simple-api"
PYTHON_DIR="$PROJECT_ROOT/python"
BENCH_VENV="$SCRIPT_DIR/.venv"
RESULTS_DIR="$SCRIPT_DIR/results"
ENV_FILE="${BENCHMARK_ENV_FILE:-$PROJECT_ROOT/benchmark-controls.env}"

ONLY=""
POSITIONAL=()
while [ $# -gt 0 ]; do
  case "$1" in
    --only)
      ONLY="$2"; shift 2
      case "$ONLY" in
        single|sharded|citus|lookup) ;;
        *) echo "ERR: --only must be one of: single, sharded, citus, lookup" >&2; exit 1 ;;
      esac
      ;;
    --help|-h)
      sed -n '2,12p' "$0"; exit 0 ;;
    *) POSITIONAL+=("$1"); shift ;;
  esac
done
set -- "${POSITIONAL[@]}"

BENCH_USERS="${1:-80}"
BENCH_SPAWN="${2:-10}"
BENCH_DURATION="${3:-180s}"

run_strategy() { [ -z "$ONLY" ] || [ "$ONLY" = "$1" ]; }

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; BLUE='\033[0;34m'; NC='\033[0m'

log()  { echo -e "${GREEN}[$(date +%H:%M:%S)]${NC} $1"; }
warn() { echo -e "${YELLOW}[$(date +%H:%M:%S)] WARN:${NC} $1"; }
err()  { echo -e "${RED}[$(date +%H:%M:%S)] ERR:${NC} $1"; }
section() {
  echo ""
  echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
  echo -e "${BLUE}  $1${NC}"
  echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
  echo ""
}

mkdir -p "$RESULTS_DIR"

# ── helpers ────────────────────────────────────────────────────────────────────

docker_compose() { docker compose --env-file "$ENV_FILE" "$@"; }

kill_spring() {
  pkill -f "spring-boot:run" 2>/dev/null || true
  pkill -f "e-commerce-simple-api" 2>/dev/null || true
  sleep 2
}

wait_spring() {
  local max=120 elapsed=0 code
  log "Waiting for Spring Boot..."
  while [ $elapsed -lt $max ]; do
    # curl returns non-zero on connection refused. `|| code="000"` neutralizes set -e.
    # Require first digit >= 1 to reject "000". Hit a real controller route (no actuator on classpath).
    code=$(curl -s --connect-timeout 3 --max-time 5 -o /dev/null \
      -w "%{http_code}" "http://localhost:8080/orders/all-page?page=0&size=1" 2>/dev/null) || code="000"
    if [[ "$code" =~ ^[1-9][0-9]{2}$ ]]; then
      log "Spring Boot ready (HTTP $code)."
      return 0
    fi
    sleep 3; elapsed=$((elapsed+3)); echo -n "."
  done
  echo ""
  err "Spring Boot did not start within ${max}s"
  return 1
}

wait_healthy() {
  local compose_file="$1" max=90 elapsed=0
  log "Waiting for containers..."
  while [ $elapsed -lt $max ]; do
    local not_ready
    not_ready=$(docker_compose -f "$compose_file" ps --format json 2>/dev/null \
      | python3 -c "
import sys, json
lines = sys.stdin.read().strip()
# docker compose ps --format json outputs one JSON object per line (not an array)
not_ready = 0
for line in lines.splitlines():
    if not line.strip():
        continue
    try:
        s = json.loads(line)
        h = s.get('Health','')
        if h and h != 'healthy':
            not_ready += 1
    except:
        pass
print(not_ready)
" 2>/dev/null || echo "0")
    if [ "$not_ready" = "0" ]; then
      log "Containers healthy."
      return 0
    fi
    sleep 5; elapsed=$((elapsed+5)); echo -n "."
  done
  echo ""
  warn "Timeout waiting for health — proceeding anyway."
}

run_locust() {
  local strategy="$1"
  local ts="$2"
  local out="$RESULTS_DIR/${strategy}_${ts}"
  log "Running Locust → $out"
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
  log "Results: ${out}_stats.csv"
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

dump_db_logs() {
  local strategy="$1"
  local ts="$2"
  local compose_file="$3"
  local log_path="$RESULTS_DIR/${strategy}_${ts}_db.log"
  docker_compose -f "$compose_file" logs --no-color --timestamps > "$log_path" 2>&1 || true
  log "DB log → $log_path"
}

# ── Strategy 1: Single DB ───────────────────────────────────────────────────

if run_strategy single; then
  section "1/4  Single DB"
  TS=$(date +%Y%m%d_%H%M%S)
  COMPOSE="$PROJECT_ROOT/00-single-db/docker-compose.benchmark.yaml"
  cd "$PROJECT_ROOT/00-single-db"
  docker_compose -f docker-compose.benchmark.yaml up -d
  wait_healthy "$COMPOSE"

  kill_spring
  start_spring "single" "single" "$TS"
  wait_spring

  run_locust "single" "$TS"

  kill $SPRING_PID 2>/dev/null || true; kill_spring
  dump_db_logs "single" "$TS" "$COMPOSE"
  cd "$PROJECT_ROOT/00-single-db"
  docker_compose -f docker-compose.benchmark.yaml down
  log "Single DB done."
fi

# ── Strategy 2: Manual Sharding ────────────────────────────────────────────

if run_strategy sharded; then
  section "2/4  Manual Sharding"
  TS=$(date +%Y%m%d_%H%M%S)
  COMPOSE="$PROJECT_ROOT/01-manual-sharding/docker-compose.benchmark.yaml"
  cd "$PROJECT_ROOT/01-manual-sharding"
  docker_compose -f docker-compose.benchmark.yaml up -d
  wait_healthy "$COMPOSE"

  kill_spring
  start_spring "sharded" "sharded" "$TS"
  wait_spring

  run_locust "sharded" "$TS"

  kill $SPRING_PID 2>/dev/null || true; kill_spring
  dump_db_logs "sharded" "$TS" "$COMPOSE"
  cd "$PROJECT_ROOT/01-manual-sharding"
  docker_compose -f docker-compose.benchmark.yaml down
  log "Manual Sharding done."
fi

# ── Strategy 3: Citus ──────────────────────────────────────────────────────

if run_strategy citus; then
  section "3/4  Citus"
  TS=$(date +%Y%m%d_%H%M%S)
  COMPOSE="$PROJECT_ROOT/02-citus-sharding/docker-compose.benchmark.yaml"
  cd "$PROJECT_ROOT/02-citus-sharding"
  docker_compose -f docker-compose.benchmark.yaml up -d
  wait_healthy "$COMPOSE"

  # Re-register workers (needed after container restart even with existing volume)
  log "Re-registering Citus workers..."
  sleep 5
  docker exec master psql -U postgres -d mydb -c "ALTER SYSTEM SET citus.node_conninfo = 'sslmode=disable';" 2>/dev/null || true
  docker exec master psql -U postgres -d mydb -c "SELECT pg_reload_conf();" 2>/dev/null || true
  for i in 1 2 3 4; do
    docker exec "worker-$i" psql -U postgres -d mydb -c "ALTER SYSTEM SET citus.node_conninfo = 'sslmode=disable';" 2>/dev/null || true
    docker exec "worker-$i" psql -U postgres -d mydb -c "SELECT pg_reload_conf();" 2>/dev/null || true
  done
  docker exec master psql -U postgres -d mydb -c "SELECT citus_set_coordinator_host('master', 5432);" 2>/dev/null || true
  for i in 1 2 3 4; do
    docker exec master psql -U postgres -d mydb \
      -c "SELECT citus_add_node('worker-$i', 5432);" 2>/dev/null || true
  done
  log "Citus nodes registered."

  kill_spring
  start_spring "citus" "single" "$TS"
  wait_spring

  run_locust "citus" "$TS"

  kill $SPRING_PID 2>/dev/null || true; kill_spring
  dump_db_logs "citus" "$TS" "$COMPOSE"
  cd "$PROJECT_ROOT/02-citus-sharding"
  docker_compose -f docker-compose.benchmark.yaml down
  log "Citus done."
fi

# ── Strategy 4: Lookup Table ───────────────────────────────────────────────

if run_strategy lookup; then
  section "4/4  Lookup Table"
  TS=$(date +%Y%m%d_%H%M%S)
  COMPOSE="$PROJECT_ROOT/03-manual-sharding-lookup-table/docker-compose.benchmark.yaml"
  cd "$PROJECT_ROOT/03-manual-sharding-lookup-table"
  docker_compose -f docker-compose.benchmark.yaml up -d
  wait_healthy "$COMPOSE"

  kill_spring
  start_spring "lookup" "lookup" "$TS"
  wait_spring

  run_locust "lookup" "$TS"

  kill $SPRING_PID 2>/dev/null || true; kill_spring
  dump_db_logs "lookup" "$TS" "$COMPOSE"
  cd "$PROJECT_ROOT/03-manual-sharding-lookup-table"
  docker_compose -f docker-compose.benchmark.yaml down
  log "Lookup Table done."
fi

# ── Summary ────────────────────────────────────────────────────────────────

section "All benchmarks complete"
log "Results in $RESULTS_DIR:"
ls -lt "$RESULTS_DIR"/*_stats.csv 2>/dev/null | head -8
