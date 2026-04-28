#!/bin/bash

# =============================================================================
# Automated Benchmark Runner for All Database Sharding Strategies
# =============================================================================
#
# This script automates the complete benchmark process:
# 1. Cleanup existing containers/volumes
# 2. For each strategy: populate DB -> stop containers -> start benchmark containers -> run benchmark
#
# Usage:
#   ./run_all_benchmarks.sh [options]
#
# Options:
#   --users N           Number of users to generate (default: 1000)
#   --products N        Number of products to generate (default: 500)
#   --orders-per-user N Orders per user (default: 5)
#   --items-per-order N Items per order (default: 3)
#   --bench-users N     Locust concurrent users (default: 50)
#   --bench-spawn N     Locust spawn rate (default: 10)
#   --bench-duration S  Benchmark duration, e.g., 60s, 2m (default: 60s)
#   --skip-single       Skip single database benchmark
#   --skip-sharded      Skip manual sharding benchmark
#   --skip-citus        Skip Citus benchmark
#   --skip-lookup       Skip lookup table benchmark
#   --only STRATEGY     Run only specified strategy (single|sharded|citus|lookup)
#   --help              Show this help message
#
# =============================================================================

set -e

# Script is in benchmark/, project root is one level up
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
JAVA_DIR="$PROJECT_ROOT/java/e-commerce-simple-api"
PYTHON_DIR="$PROJECT_ROOT/python"
BENCH_VENV="$SCRIPT_DIR/.venv"
BENCHMARK_DIR="$SCRIPT_DIR"
ENV_FILE="${BENCHMARK_ENV_FILE:-$PROJECT_ROOT/benchmark-controls.env}"

# Default data generation parameters
USERS=250000
PRODUCTS=2000
ORDERS_PER_USER=5
ITEMS_PER_ORDER=5

# Default benchmark parameters
BENCH_USERS=80
BENCH_SPAWN=15
BENCH_DURATION="180s"

# Strategy flags
RUN_SINGLE=true
RUN_SHARDED=true
RUN_CITUS=true
RUN_LOOKUP=true

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# =============================================================================
# Helper Functions
# =============================================================================

print_banner() {
    echo -e "${CYAN}"
    echo "╔══════════════════════════════════════════════════════════════════════╗"
    echo "║          Automated Database Sharding Benchmark Suite                 ║"
    echo "╚══════════════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

print_section() {
    echo ""
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BLUE}  $1${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
}

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

show_help() {
    head -40 "$0" | tail -35
    exit 0
}

# =============================================================================
# Parse Arguments
# =============================================================================

while [[ $# -gt 0 ]]; do
    case $1 in
        --users) USERS="$2"; shift 2 ;;
        --products) PRODUCTS="$2"; shift 2 ;;
        --orders-per-user) ORDERS_PER_USER="$2"; shift 2 ;;
        --items-per-order) ITEMS_PER_ORDER="$2"; shift 2 ;;
        --bench-users) BENCH_USERS="$2"; shift 2 ;;
        --bench-spawn) BENCH_SPAWN="$2"; shift 2 ;;
        --bench-duration) BENCH_DURATION="$2"; shift 2 ;;
        --skip-single) RUN_SINGLE=false; shift ;;
        --skip-sharded) RUN_SHARDED=false; shift ;;
        --skip-citus) RUN_CITUS=false; shift ;;
        --skip-lookup) RUN_LOOKUP=false; shift ;;
        --only)
            RUN_SINGLE=false; RUN_SHARDED=false; RUN_CITUS=false; RUN_LOOKUP=false
            case $2 in
                single) RUN_SINGLE=true ;;
                sharded) RUN_SHARDED=true ;;
                citus) RUN_CITUS=true ;;
                lookup) RUN_LOOKUP=true ;;
                *) log_error "Unknown strategy: $2"; exit 1 ;;
            esac
            shift 2
            ;;
        --help|-h) show_help ;;
        *) log_error "Unknown option: $1"; show_help ;;
    esac
done

# =============================================================================
# Prerequisite Checks
# =============================================================================

check_prerequisites() {
    print_section "Checking Prerequisites"

    # Check Docker
    if ! command -v docker &> /dev/null; then
        log_error "Docker is not installed"
        exit 1
    fi
    log_info "Docker: OK"

    # Check Docker Compose
    if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
        log_error "Docker Compose is not installed"
        exit 1
    fi
    log_info "Docker Compose: OK"

    # Check Python venv (db_setup)
    if [ ! -d "$PYTHON_DIR/.venv" ]; then
        log_error "Python virtual environment not found at $PYTHON_DIR/.venv"
        log_info "Create it with: cd $PYTHON_DIR && python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt"
        exit 1
    fi
    log_info "Python venv: OK"

    # Check benchmark venv (locust)
    if [ ! -d "$BENCH_VENV" ]; then
        log_error "Benchmark virtual environment not found at $BENCH_VENV"
        log_info "Create it with: cd $SCRIPT_DIR && python -m venv .venv && .venv/bin/pip install -r requirements.txt"
        exit 1
    fi
    log_info "Benchmark venv: OK"

    # Check Locust
    if ! "$BENCH_VENV/bin/locust" --version &> /dev/null; then
        log_error "Locust not installed in benchmark venv ($BENCH_VENV)"
        log_info "Install with: $BENCH_VENV/bin/pip install -r $SCRIPT_DIR/requirements.txt"
        exit 1
    fi
    log_info "Locust: OK"

    # Check Maven
    if ! command -v mvn &> /dev/null; then
        log_error "Maven is not installed"
        exit 1
    fi
    log_info "Maven: OK"

    # Check Java project
    if [ ! -f "$JAVA_DIR/pom.xml" ]; then
        log_error "Java project not found at $JAVA_DIR"
        exit 1
    fi
    log_info "Java project: OK"
}

# =============================================================================
# Docker Compose Helper (handles both v1 and v2)
# =============================================================================

docker_compose_cmd() {
    if docker compose version &> /dev/null 2>&1; then
        docker compose --env-file "$ENV_FILE" "$@"
    else
        docker-compose --env-file "$ENV_FILE" "$@"
    fi
}

# =============================================================================
# Wait for containers to be healthy
# =============================================================================

wait_for_healthy() {
    local compose_file=$1
    local max_wait=${2:-120}
    local elapsed=0

    log_info "Waiting for containers to be healthy (max ${max_wait}s)..."

    while [ $elapsed -lt $max_wait ]; do
        # Check if all services are healthy
        local unhealthy=$(docker_compose_cmd -f "$compose_file" ps --format json 2>/dev/null | \
            grep -c '"Health": "' | grep -v '"Health": "healthy"' || echo "0")

        if [ "$unhealthy" = "0" ]; then
            # Alternative check using docker ps
            local all_healthy=true
            for container in $(docker_compose_cmd -f "$compose_file" ps -q 2>/dev/null); do
                local health=$(docker inspect --format='{{.State.Health.Status}}' "$container" 2>/dev/null || echo "none")
                if [ "$health" != "healthy" ] && [ "$health" != "none" ]; then
                    all_healthy=false
                    break
                fi
            done

            if $all_healthy; then
                log_info "All containers are healthy!"
                return 0
            fi
        fi

        sleep 5
        elapsed=$((elapsed + 5))
        echo -n "."
    done

    echo ""
    log_warn "Timeout waiting for containers. Proceeding anyway..."
    return 0
}

# =============================================================================
# Wait for Spring Boot to start
# =============================================================================

wait_for_spring_boot() {
    local max_wait=${1:-120}
    local elapsed=0

    log_info "Waiting for Spring Boot to start (max ${max_wait}s)..."

    while [ $elapsed -lt $max_wait ]; do
        # Check if app responds (just verify server is accepting connections)
        if curl -s --connect-timeout 2 "http://localhost:8080" > /dev/null 2>&1; then
            log_info "Spring Boot is ready!"
            return 0
        fi
        sleep 3
        elapsed=$((elapsed + 3))
        echo -n "."
    done

    echo ""
    log_error "Spring Boot failed to start within ${max_wait}s"
    return 1
}

# =============================================================================
# Kill any existing Spring Boot process
# =============================================================================

kill_spring_boot() {
    log_info "Stopping any running Spring Boot instances..."
    pkill -f "spring-boot:run" 2>/dev/null || true
    pkill -f "e-commerce-simple-api" 2>/dev/null || true
    # Give it a moment to die
    sleep 2
}

# =============================================================================
# Run benchmark for a single strategy
# =============================================================================

run_strategy_benchmark() {
    local strategy_name=$1
    local strategy_dir=$2
    local compose_file=$3
    local benchmark_compose=$4
    local python_mode=$5
    local spring_profile=$6

    print_section "Strategy: $strategy_name"

    log_info "Configuration:"
    log_info "  - Directory: $strategy_dir"
    log_info "  - Compose file: $compose_file"
    log_info "  - Benchmark compose: $benchmark_compose"
    log_info "  - Python mode: $python_mode"
    log_info "  - Spring profile: $spring_profile"
    echo ""

    # Step 1: Start regular containers
    log_info "Step 1/6: Starting database containers..."
    cd "$strategy_dir"
    docker_compose_cmd -f "$compose_file" up -d

    # Step 2: Wait for healthy
    log_info "Step 2/6: Waiting for database to be ready..."
    wait_for_healthy "$strategy_dir/$compose_file" 120

    # Extra wait for database initialization
    sleep 5

    # Step 3: Populate database
    log_info "Step 3/6: Populating database with test data..."
    cd "$PYTHON_DIR"
    source .venv/bin/activate
    python db_setup.py \
        --mode "$python_mode" \
        --users "$USERS" \
        --products "$PRODUCTS" \
        --orders-per-user "$ORDERS_PER_USER" \
        --items-per-order "$ITEMS_PER_ORDER"
    deactivate

    # Step 4: Stop regular containers and start benchmark containers
    log_info "Step 4/6: Switching to benchmark containers (resource-constrained)..."
    cd "$strategy_dir"
    docker_compose_cmd -f "$compose_file" down

    # Small delay before starting benchmark containers
    sleep 2

    docker_compose_cmd -f "$benchmark_compose" up -d
    wait_for_healthy "$strategy_dir/$benchmark_compose" 120

    # Step 5: Start Spring Boot
    log_info "Step 5/6: Starting Spring Boot application..."
    kill_spring_boot
    cd "$JAVA_DIR"

    # Start Spring Boot in background
    SPRING_PROFILES_ACTIVE="$spring_profile" mvn spring-boot:run \
        -Dspring-boot.run.profiles="$spring_profile" \
        > /tmp/spring-boot-$strategy_name.log 2>&1 &
    SPRING_PID=$!

    if ! wait_for_spring_boot 180; then
        log_error "Spring Boot failed to start. Check /tmp/spring-boot-$strategy_name.log"
        kill $SPRING_PID 2>/dev/null || true
        return 1
    fi

    # Step 6: Run benchmark
    log_info "Step 6/6: Running Locust benchmark..."
    cd "$BENCHMARK_DIR"
    source "$BENCH_VENV/bin/activate"

    "$BENCH_VENV/bin/locust" \
        -f locustfile.py \
        --host="http://localhost:8080" \
        --users "$BENCH_USERS" \
        --spawn-rate "$BENCH_SPAWN" \
        --run-time "$BENCH_DURATION" \
        --headless \
        --csv="results/${strategy_name}_$(date +%Y%m%d_%H%M%S)" \
        --html="results/${strategy_name}_$(date +%Y%m%d_%H%M%S).html" \
        2>&1 | tee "results/${strategy_name}_$(date +%Y%m%d_%H%M%S).log"

    deactivate

    # Cleanup
    log_info "Cleaning up $strategy_name..."
    kill $SPRING_PID 2>/dev/null || true
    kill_spring_boot
    cd "$strategy_dir"
    docker_compose_cmd -f "$benchmark_compose" down

    log_info "$strategy_name benchmark complete!"
    echo ""
}

# =============================================================================
# Main Execution
# =============================================================================

main() {
    print_banner

    log_info "Benchmark Configuration:"
    log_info "  Data: $USERS users, $PRODUCTS products, $ORDERS_PER_USER orders/user, $ITEMS_PER_ORDER items/order"
    log_info "  Load Test: $BENCH_USERS concurrent users, $BENCH_SPAWN spawn/s, $BENCH_DURATION duration"
    log_info "  Strategies: single=$RUN_SINGLE, sharded=$RUN_SHARDED, citus=$RUN_CITUS, lookup=$RUN_LOOKUP"
    echo ""

    check_prerequisites

    # Create results directory
    mkdir -p "$BENCHMARK_DIR/results"

    # Run cleanup
    print_section "Initial Cleanup"
    log_info "Running cleanup script..."
    cd "$PROJECT_ROOT"
    bash cleanup.sh

    # Track start time
    TOTAL_START=$(date +%s)

    # =========================================================================
    # Strategy 1: Single Database
    # =========================================================================
    if $RUN_SINGLE; then
        run_strategy_benchmark \
            "single" \
            "$PROJECT_ROOT/00-single-db" \
            "docker-compose.yaml" \
            "docker-compose.benchmark.yaml" \
            "single" \
            "single"

        # Cleanup between strategies
        bash "$PROJECT_ROOT/cleanup.sh"
    fi

    # =========================================================================
    # Strategy 2: Manual Sharding
    # =========================================================================
    if $RUN_SHARDED; then
        run_strategy_benchmark \
            "sharded" \
            "$PROJECT_ROOT/01-manual-sharding" \
            "docker-compose.yaml" \
            "docker-compose.benchmark.yaml" \
            "sharded" \
            "sharded"

        bash "$PROJECT_ROOT/cleanup.sh"
    fi

    # =========================================================================
    # Strategy 3: Citus Sharding
    # =========================================================================
    if $RUN_CITUS; then
        print_section "Strategy: Citus"
        log_warn "Citus requires special setup for distributed tables."
        log_warn "The application uses 'single' profile since Citus master handles distribution."
        log_info "If tables are not set up as distributed, this will benchmark Citus as a single node."
        echo ""

        run_strategy_benchmark \
            "citus" \
            "$PROJECT_ROOT/02-citus-sharding" \
            "docker-compose-sharded-citus.yaml" \
            "docker-compose.benchmark.yaml" \
            "single" \
            "single"

        bash "$PROJECT_ROOT/cleanup.sh"
    fi

    # =========================================================================
    # Strategy 4: Lookup Table Sharding
    # =========================================================================
    if $RUN_LOOKUP; then
        run_strategy_benchmark \
            "lookup" \
            "$PROJECT_ROOT/03-manual-sharding-lookup-table" \
            "docker-compose.yaml" \
            "docker-compose.benchmark.yaml" \
            "sharded-lookup-table" \
            "lookup"

        bash "$PROJECT_ROOT/cleanup.sh"
    fi

    # =========================================================================
    # Summary
    # =========================================================================
    TOTAL_END=$(date +%s)
    TOTAL_ELAPSED=$((TOTAL_END - TOTAL_START))

    print_section "Benchmark Suite Complete!"

    log_info "Total runtime: $((TOTAL_ELAPSED / 60)) minutes $((TOTAL_ELAPSED % 60)) seconds"
    log_info ""
    log_info "Results saved to: $BENCHMARK_DIR/results/"
    log_info ""
    log_info "View HTML reports:"
    ls -lt "$BENCHMARK_DIR/results/"*.html 2>/dev/null | head -10
    echo ""
    echo -e "${GREEN}Enjoy your movie! 🎬${NC}"
}

# Run main
main "$@"
