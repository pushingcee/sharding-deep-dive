#!/bin/bash

# Database Sharding Benchmark Runner
#
# This script runs Locust load tests against the Spring Boot API
# and saves results for comparison across different sharding strategies.
#
# Prerequisites:
#   1. Python virtual environment with locust installed
#   2. Database containers running (docker-compose up -d)
#   3. Spring Boot API running (mvn spring-boot:run)
#
# Usage:
#   ./run_benchmark.sh [strategy] [users] [duration]
#
# Examples:
#   ./run_benchmark.sh single 50 60      # Test single DB with 50 users for 60s
#   ./run_benchmark.sh sharded 100 120   # Test sharded DB with 100 users for 120s
#   ./run_benchmark.sh                   # Interactive mode (Locust web UI)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
RESULTS_DIR="$SCRIPT_DIR/results"

# Default values
STRATEGY="${1:-interactive}"
USERS="${2:-150}"
SPAWN_RATE="${3:-15}"
DURATION="${4:-180s}"
HOST="${5:-http://localhost:8080}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_header() {
    echo -e "${BLUE}"
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║           Database Sharding Benchmark Runner                 ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

print_usage() {
    echo "Usage: $0 [strategy] [users] [spawn_rate] [duration] [host]"
    echo ""
    echo "Strategies:"
    echo "  interactive  - Launch Locust web UI (default)"
    echo "  single       - Benchmark single database"
    echo "  sharded      - Benchmark manual sharding"
    echo "  citus        - Benchmark Citus sharding"
    echo "  lookup       - Benchmark lookup table sharding"
    echo "  all          - Run all benchmarks sequentially"
    echo ""
    echo "Parameters:"
    echo "  users        - Number of concurrent users (default: 150)"
    echo "  spawn_rate   - Users spawned per second (default: 15)"
    echo "  duration     - Test duration, e.g., 60s, 5m (default: 180s)"
    echo "  host         - API host URL (default: http://localhost:8080)"
    echo ""
    echo "Examples:"
    echo "  $0                           # Interactive web UI"
    echo "  $0 single 150 15 180s        # Single DB, 150 users, 3 minutes"
    echo "  $0 sharded 200 20 180s       # Sharded, 200 users, 3 minutes"
    echo "  $0 all 150 15 180s           # Run all strategies"
}

check_prerequisites() {
    echo -e "${YELLOW}Checking prerequisites...${NC}"

    # Check if locust is installed
    if ! command -v locust &> /dev/null; then
        echo -e "${RED}Error: locust is not installed${NC}"
        echo "Install it with: pip install locust"
        exit 1
    fi

    # Check if API is responding
    if ! curl -s --connect-timeout 5 "$HOST/actuator/health" > /dev/null 2>&1; then
        echo -e "${RED}Warning: API at $HOST may not be running${NC}"
        echo "Make sure to start the Spring Boot application:"
        echo "  cd java/e-commerce-simple-api && mvn spring-boot:run"
        echo ""
        read -p "Continue anyway? (y/N) " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 1
        fi
    else
        echo -e "${GREEN}API is responding at $HOST${NC}"
    fi
}

run_benchmark() {
    local strategy=$1
    local timestamp=$(date +%Y%m%d_%H%M%S)
    local result_file="$RESULTS_DIR/${strategy}_${timestamp}"

    mkdir -p "$RESULTS_DIR"

    echo -e "${GREEN}Running benchmark: $strategy${NC}"
    echo "  Users: $USERS"
    echo "  Spawn rate: $SPAWN_RATE/s"
    echo "  Duration: $DURATION"
    echo "  Results: $result_file"
    echo ""

    locust -f "$SCRIPT_DIR/locustfile.py" \
           --host="$HOST" \
           --users "$USERS" \
           --spawn-rate "$SPAWN_RATE" \
           --run-time "$DURATION" \
           --headless \
           --csv="$result_file" \
           --html="$result_file.html" \
           2>&1 | tee "$result_file.log"

    echo ""
    echo -e "${GREEN}Benchmark complete!${NC}"
    echo "Results saved to:"
    echo "  - $result_file.html (visual report)"
    echo "  - ${result_file}_stats.csv (statistics)"
    echo "  - ${result_file}_stats_history.csv (time series)"
    echo "  - $result_file.log (console output)"
}

run_interactive() {
    echo -e "${GREEN}Starting Locust web UI...${NC}"
    echo "Open http://localhost:8089 in your browser"
    echo ""
    locust -f "$SCRIPT_DIR/locustfile.py" --host="$HOST"
}

compare_results() {
    echo -e "${BLUE}Recent benchmark results:${NC}"
    echo ""

    if [ -d "$RESULTS_DIR" ]; then
        ls -lt "$RESULTS_DIR"/*.html 2>/dev/null | head -10 || echo "No results found"
    else
        echo "No results directory found"
    fi
}

# Main script
print_header

case "$STRATEGY" in
    interactive)
        check_prerequisites
        run_interactive
        ;;
    single|sharded|citus|lookup)
        check_prerequisites
        run_benchmark "$STRATEGY"
        ;;
    all)
        check_prerequisites
        echo -e "${YELLOW}Running benchmarks for all strategies...${NC}"
        echo "Note: You'll need to switch database configurations manually between runs"
        echo ""

        for strat in single sharded citus lookup; do
            echo -e "${BLUE}=== Strategy: $strat ===${NC}"
            read -p "Press Enter when $strat database is ready, or 's' to skip: " -n 1 -r
            echo
            if [[ ! $REPLY =~ ^[Ss]$ ]]; then
                run_benchmark "$strat"
            else
                echo "Skipping $strat"
            fi
            echo ""
        done

        compare_results
        ;;
    results)
        compare_results
        ;;
    help|--help|-h)
        print_usage
        ;;
    *)
        echo -e "${RED}Unknown strategy: $STRATEGY${NC}"
        print_usage
        exit 1
        ;;
esac
