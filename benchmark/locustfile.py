"""
Locust load testing configuration for database sharding benchmark.

This file defines load test scenarios to compare performance across:
- Single database
- Manual sharding (hash-based)
- Citus sharding
- Lookup table sharding

Usage:
    # Start the web UI (recommended for interactive testing)
    locust -f locustfile.py --host=http://localhost:8080

    # Headless mode with specific parameters
    locust -f locustfile.py --host=http://localhost:8080 \
           --users 50 --spawn-rate 10 --run-time 60s --headless

    # Run specific user class only
    locust -f locustfile.py --host=http://localhost:8080 -T HeavyAnalyticsUser

Key Metrics to Compare:
    - Response time (p50, p95, p99)
    - Requests per second (RPS)
    - Failure rate
    - The /analytics endpoint is the best for comparing sharding benefits
      as it executes complex cross-table queries
"""

import random
import logging
from locust import HttpUser, task, between, events
from locust.runners import MasterRunner

# Sample UUIDs - these will be populated from the database
# In a real scenario, you'd fetch these from the API or database first
SAMPLE_USER_IDS = []
SAMPLE_PRODUCT_IDS = []
SAMPLE_ORDER_IDS = []

logger = logging.getLogger(__name__)


@events.init.add_listener
def on_locust_init(environment, **kwargs):
    """Initialize test data when Locust starts."""
    if isinstance(environment.runner, MasterRunner):
        logger.info("Running on master node, skipping data fetch")
        return

    logger.info("Locust initialized - fetching sample IDs from API...")
    # Note: Sample IDs should be pre-populated or fetched at test start
    # For now, tests will use random UUIDs which may return 404s
    # This is intentional to also test error handling performance


class QuickReadUser(HttpUser):
    """
    Simulates users performing quick read operations.

    This represents typical API usage patterns:
    - Fetching user profiles
    - Looking up products
    - Checking order status

    Use this to measure baseline read performance.
    """

    weight = 3  # 3x more likely to spawn than other user types
    wait_time = between(0.5, 2)  # Wait 0.5-2 seconds between requests

    def on_start(self):
        """Called when a simulated user starts."""
        # Try to fetch some real IDs from the API
        self._fetch_sample_ids()

    def _fetch_sample_ids(self):
        """Attempt to fetch sample IDs from paginated endpoints."""
        global SAMPLE_USER_IDS, SAMPLE_ORDER_IDS

        try:
            # Fetch some orders to get user_ids and order_ids
            response = self.client.get("/orders/all-page?page=0&size=100",
                                       name="/orders/all-page [init]")
            if response.status_code == 200:
                data = response.json()
                content = data.get("content", [])
                for order in content[:50]:
                    # Handle snake_case field names from Java entities
                    order_id = order.get("order_id")
                    if order_id and order_id not in SAMPLE_ORDER_IDS:
                        SAMPLE_ORDER_IDS.append(order_id)
                    # User is nested object in Order entity
                    user = order.get("user", {})
                    user_id = user.get("user_id") if user else None
                    if user_id and user_id not in SAMPLE_USER_IDS:
                        SAMPLE_USER_IDS.append(user_id)
                logger.info(f"Fetched {len(SAMPLE_USER_IDS)} user IDs and {len(SAMPLE_ORDER_IDS)} order IDs")
        except Exception as e:
            logger.warning(f"Could not fetch sample IDs: {e}")

    @task(5)
    def get_user_by_id(self):
        """Fetch a user by UUID - tests single-row lookup performance."""
        if SAMPLE_USER_IDS:
            user_id = random.choice(SAMPLE_USER_IDS)
            self.client.get(f"/users/{user_id}", name="/users/{uuid}")
        else:
            # Use a random UUID if we don't have samples
            self.client.get(f"/users/00000000-0000-0000-0000-000000000001",
                           name="/users/{uuid}")

    @task(3)
    def get_orders_by_user(self):
        """Fetch orders for a user - tests co-located data retrieval."""
        if SAMPLE_USER_IDS:
            user_id = random.choice(SAMPLE_USER_IDS)
            self.client.get(f"/orders/user/{user_id}", name="/orders/user/{uuid}")
        else:
            self.client.get(f"/orders/user/00000000-0000-0000-0000-000000000001",
                           name="/orders/user/{uuid}")

    @task(2)
    def get_order_by_id(self):
        """Fetch a specific order - tests single-row lookup."""
        if SAMPLE_ORDER_IDS:
            order_id = random.choice(SAMPLE_ORDER_IDS)
            self.client.get(f"/orders/{order_id}", name="/orders/{uuid}")
        else:
            self.client.get(f"/orders/00000000-0000-0000-0000-000000000001",
                           name="/orders/{uuid}")

    @task(1)
    def get_orders_paginated(self):
        """Fetch paginated orders - tests scan performance."""
        page = random.randint(0, 10)
        size = random.choice([10, 20, 50])
        self.client.get(f"/orders/all-page?page={page}&size={size}",
                       name="/orders/all-page")


class HeavyAnalyticsUser(HttpUser):
    """
    Simulates users running heavy analytics queries.

    THIS IS THE KEY BENCHMARK for comparing sharding strategies.

    The /analytics endpoint runs a complex query with:
    - Multiple table JOINs (users, orders, products, order_items)
    - Aggregations (COUNT, SUM, AVG, MAX)
    - CTEs (Common Table Expressions)
    - Date range filtering

    In sharded setups, this query runs in parallel across shards,
    demonstrating the scalability benefits of horizontal partitioning.
    """

    weight = 1  # Less frequent than quick reads
    wait_time = between(2, 5)  # Longer wait between heavy queries

    @task
    def run_analytics(self):
        """
        Execute the heavy cross-shard analytics query.

        Monitor the X-Execution-Time-Ms header for server-side timing.
        Compare this across different sharding strategies to see benefits.
        """
        with self.client.get("/analytics",
                            name="/analytics [HEAVY]",
                            catch_response=True) as response:
            if response.status_code == 200:
                # Log server-side execution time if available
                exec_time = response.headers.get("X-Execution-Time-Ms")
                if exec_time:
                    logger.debug(f"Analytics query server time: {exec_time}ms")
                response.success()
            else:
                response.failure(f"Analytics failed: {response.status_code}")


class MixedWorkloadUser(HttpUser):
    """
    Simulates realistic mixed workload with reads and analytics.

    This represents a typical production scenario where most requests
    are simple reads, but occasional analytics queries create load spikes.
    """

    weight = 2
    wait_time = between(1, 3)

    @task(10)
    def quick_user_lookup(self):
        """High-frequency user lookups."""
        if SAMPLE_USER_IDS:
            user_id = random.choice(SAMPLE_USER_IDS)
            self.client.get(f"/users/{user_id}", name="/users/{uuid}")

    @task(5)
    def quick_order_lookup(self):
        """Medium-frequency order lookups."""
        if SAMPLE_ORDER_IDS:
            order_id = random.choice(SAMPLE_ORDER_IDS)
            self.client.get(f"/orders/{order_id}", name="/orders/{uuid}")

    @task(1)
    def occasional_analytics(self):
        """Low-frequency but heavy analytics."""
        self.client.get("/analytics", name="/analytics [HEAVY]")


# Custom event handlers for better reporting
@events.request.add_listener
def on_request(request_type, name, response_time, response_length,
               response, context, exception, **kwargs):
    """Log details for analytics requests to help with comparison."""
    if "[HEAVY]" in name and response is not None:
        exec_time = response.headers.get("X-Execution-Time-Ms", "N/A")
        logger.info(f"Analytics: client={response_time:.0f}ms, server={exec_time}ms")


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """Print summary when test stops."""
    logger.info("=" * 60)
    logger.info("BENCHMARK COMPLETE")
    logger.info("=" * 60)
    logger.info("Compare these results across different database configurations:")
    logger.info("  1. Single DB:     docker-compose -f 00-single-db/docker-compose.benchmark.yaml")
    logger.info("  2. Manual Shard:  docker-compose -f 01-manual-sharding/docker-compose.benchmark.yaml")
    logger.info("  3. Citus:         docker-compose -f 02-citus-sharding/docker-compose.benchmark.yaml")
    logger.info("  4. Lookup Table:  docker-compose -f 03-manual-sharding-lookup-table/docker-compose.benchmark.yaml")
    logger.info("=" * 60)
