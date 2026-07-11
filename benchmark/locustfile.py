"""
Locust load testing configuration for database sharding benchmark.

Compares performance across:
- Single database
- Manual sharding (hash-based)
- Citus sharding
- Lookup table sharding

Determinism
-----------
Every run against every DB must generate the *same* sequence of requests
and parameters, so differences in measured latency come from the DB only.
To achieve that:

  * Global ``LOAD_SEED`` seeds the prefetch-pool shuffle.
  * Each VU gets its own ``random.Random`` seeded from ``LOAD_SEED + vu_id``,
    so the stream of user/order IDs and date ranges it draws is reproducible.
  * ``wait_time`` uses the same per-VU RNG, so pacing is also reproducible.
  * Analytics date ranges are computed relative to ``ANCHOR_DATE`` (not
    ``date.today()``), so running the benchmark on different days still
    produces identical params.

Usage
-----
    locust -f locustfile.py --host=http://localhost:8080 \\
           --users 50 --spawn-rate 10 --run-time 60s --headless

Override the seed or anchor via env:
    LOAD_SEED=42 ANCHOR_DATE=2026-01-01 locust ...
"""

import csv
import math
import os
import random
import logging
import itertools
import datetime as dt
from collections import defaultdict
from pathlib import Path
from typing import Iterator, Optional
from locust import HttpUser, task, events
from locust.runners import MasterRunner

# Determinism knobs -----------------------------------------------------------
LOAD_SEED = int(os.environ.get("LOAD_SEED", "1337"))
# Fixed anchor so date ranges don't drift between runs on different days.
ANCHOR_DATE = dt.date.fromisoformat(os.environ.get("ANCHOR_DATE", "2026-01-01"))

# Pool sizes: what fraction of seeded rows to sample for workload rotation.
# Wider pool => harder to cache the working set => more prod-like.
# Percentage-based so the pool scales with DB size — a 10k-user seed still
# gets a usable pool without a fixed 50k floor producing "not enough rows".
USER_POOL_PCT = float(os.environ.get("USER_POOL_PCT", "0.10"))
ORDER_POOL_PCT = float(os.environ.get("ORDER_POOL_PCT", "0.10"))

# CSV data source for ID prefetch. Same files used by the seeder.
DATA_DIR = Path(os.environ.get("BENCH_DATA_DIR", Path(__file__).resolve().parent.parent / "data"))

# Populated once at test_start from the API
SAMPLE_USER_IDS: list[str] = []
SAMPLE_ORDER_IDS: list[str] = []

# Server-side execution times (ms) per endpoint name, taken from the
# X-Execution-Time-Ms response header. client_latency - server_time is the
# cost of everything above the database (routing, fan-out, coordinator
# aggregation, serialization) — the quantity this benchmark compares.
# Written to <csv_prefix>_server_timing.csv at test stop.
# NOTE: single-process runs only; distributed workers would each write the
# same file.
SERVER_TIMINGS: dict[str, list[float]] = defaultdict(list)

# Global VU-id allocator — each HttpUser instance claims a unique id on start,
# which seeds its local RNG. Using a counter (rather than id(self)) keeps the
# seed sequence identical across runs.
_vu_counter = itertools.count()

logger = logging.getLogger(__name__)


def _random_analytics_window(rng: random.Random) -> tuple[dt.date, dt.date]:
    """Pick a deterministic 30-day window within the 2 years before ANCHOR_DATE.

    Window width is fixed (30 days) so each call does comparable work.
    Start date is drawn uniformly, so different calls hit different heap
    slices and defeat any per-query result cache.
    """
    max_offset_days = 365 * 2 - 30
    offset = rng.randint(0, max_offset_days)
    window_end = ANCHOR_DATE - dt.timedelta(days=offset)
    window_start = window_end - dt.timedelta(days=30)
    return window_start, window_end


def _bernoulli_sample_first_column(path: Path, pct: float, rng: random.Random) -> list[str]:
    """Keep each row from the first column of a CSV with probability ``pct``.

    One streaming pass — no line count needed up front. Pool size scales with
    input size, so a smaller seeded DB still yields a proportional pool.
    """
    if not 0.0 < pct <= 1.0:
        raise ValueError(f"sample pct must be in (0, 1], got {pct}")
    sample: list[str] = []
    with path.open("r", newline="") as f:
        reader = csv.reader(f)
        next(reader, None)  # skip header
        for row in reader:
            if not row:
                continue
            if rng.random() < pct:
                sample.append(row[0])
    return sample


@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    """Sample a wide pool of user/order IDs from the seed CSVs before VUs start.

    Reading from disk (not the API) keeps the warm-up independent of backend
    performance, so a slow /orders/all-page on the sharded backend doesn't
    starve the measured workload.
    """
    if isinstance(environment.runner, MasterRunner):
        return

    users_csv = DATA_DIR / "users.csv"
    orders_csv = DATA_DIR / "orders.csv"
    if not users_csv.exists() or not orders_csv.exists():
        raise RuntimeError(
            f"Seed CSVs not found under {DATA_DIR}. "
            f"Set BENCH_DATA_DIR or regenerate with db_setup.py."
        )

    logger.info(
        f"Sampling ID pools from CSV (users_pct={USER_POOL_PCT:.2%}, "
        f"orders_pct={ORDER_POOL_PCT:.2%}, seed={LOAD_SEED}, anchor={ANCHOR_DATE})..."
    )
    rng = random.Random(LOAD_SEED)
    users_sampled = _bernoulli_sample_first_column(users_csv, USER_POOL_PCT, rng)
    orders_sampled = _bernoulli_sample_first_column(orders_csv, ORDER_POOL_PCT, rng)
    if not users_sampled or not orders_sampled:
        raise RuntimeError(
            f"Sampled 0 rows — check CSVs at {DATA_DIR} and *_POOL_PCT settings."
        )

    # Shuffle with the same RNG so rotation order is deterministic across runs.
    rng.shuffle(users_sampled)
    rng.shuffle(orders_sampled)
    SAMPLE_USER_IDS[:] = users_sampled
    SAMPLE_ORDER_IDS[:] = orders_sampled

    # Reset the VU counter so a second test in the same process re-seeds VUs identically.
    global _vu_counter
    _vu_counter = itertools.count()
    SERVER_TIMINGS.clear()

    logger.info(
        f"Sampling complete: {len(SAMPLE_USER_IDS)} users, "
        f"{len(SAMPLE_ORDER_IDS)} orders"
    )


class _SeededUser(HttpUser):
    """Base class that gives each VU its own deterministic RNG.

    ``wait_time`` is overridden to draw from the local RNG so pacing is
    reproducible across runs.
    """

    abstract = True
    wait_low: float = 0.5
    wait_high: float = 2.0

    def on_start(self) -> None:
        self.vu_id: int = next(_vu_counter)
        self.rng: random.Random = random.Random(LOAD_SEED + self.vu_id)

    def wait_time(self) -> float:
        return self.rng.uniform(self.wait_low, self.wait_high)


class QuickReadUser(_SeededUser):
    """Quick read operations: user/order point lookups, paginated scans."""

    weight = 3
    wait_low, wait_high = 0.5, 2.0

    @task(5)
    def get_user_by_id(self) -> None:
        user_id = self.rng.choice(SAMPLE_USER_IDS)
        self.client.get(f"/users/{user_id}", name="/users/{uuid}")

    @task(3)
    def get_orders_by_user(self) -> None:
        user_id = self.rng.choice(SAMPLE_USER_IDS)
        self.client.get(f"/orders/user/{user_id}", name="/orders/user/{uuid}")

    @task(2)
    def get_order_by_id(self) -> None:
        order_id = self.rng.choice(SAMPLE_ORDER_IDS)
        self.client.get(f"/orders/{order_id}", name="/orders/{uuid}")

    @task(1)
    def get_orders_paginated(self) -> None:
        page = self.rng.randint(0, 10)
        size = self.rng.choice([10, 20, 50])
        self.client.get(
            f"/orders/all-page?page={page}&size={size}",
            name="/orders/all-page",
        )


class HeavyAnalyticsUser(_SeededUser):
    """
    THIS IS THE KEY BENCHMARK.

    Each call picks a random 30-day window (deterministically, per VU) and
    passes it as ?from=&to=. That defeats result caching and makes each
    call exercise a different slice of the heap, so the scan is cache-
    unfriendly in the prod-like way.
    """

    weight = 1
    wait_low, wait_high = 2.0, 5.0

    @task
    def run_analytics(self) -> None:
        window_start, window_end = _random_analytics_window(self.rng)
        url = f"/analytics?from={window_start.isoformat()}&to={window_end.isoformat()}"
        with self.client.get(
            url,
            name="/analytics [HEAVY]",
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                exec_time = response.headers.get("X-Execution-Time-Ms")
                if exec_time:
                    logger.debug(f"Analytics query server time: {exec_time}ms")
                response.success()
            else:
                response.failure(f"Analytics failed: {response.status_code}")


class MixedWorkloadUser(_SeededUser):
    """Realistic mixed workload — mostly reads, occasional analytics."""

    weight = 2
    wait_low, wait_high = 1.0, 3.0

    @task(10)
    def quick_user_lookup(self) -> None:
        user_id = self.rng.choice(SAMPLE_USER_IDS)
        self.client.get(f"/users/{user_id}", name="/users/{uuid}")

    @task(5)
    def quick_order_lookup(self) -> None:
        order_id = self.rng.choice(SAMPLE_ORDER_IDS)
        self.client.get(f"/orders/{order_id}", name="/orders/{uuid}")

    @task(1)
    def occasional_analytics(self) -> None:
        window_start, window_end = _random_analytics_window(self.rng)
        url = f"/analytics?from={window_start.isoformat()}&to={window_end.isoformat()}"
        self.client.get(url, name="/analytics [HEAVY]")


@events.request.add_listener
def on_request(request_type, name, response_time, response_length,
               response, context, exception, **kwargs):
    if response is None:
        return
    exec_time = response.headers.get("X-Execution-Time-Ms")
    if exec_time is not None:
        try:
            SERVER_TIMINGS[name].append(float(exec_time))
        except ValueError:
            pass
    if "[HEAVY]" in name:
        logger.info(f"Analytics: client={response_time:.0f}ms, server={exec_time or 'N/A'}ms")


def _percentile(sorted_values: list[float], pct: float) -> float:
    """Nearest-rank percentile of an already-sorted list."""
    rank = max(1, math.ceil(pct / 100 * len(sorted_values)))
    return sorted_values[rank - 1]


def _write_server_timing_csv(csv_prefix: str) -> None:
    path = f"{csv_prefix}_server_timing.csv"
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "Name", "Request Count", "Min Server Time (ms)", "Median Server Time (ms)",
            "95% Server Time (ms)", "Max Server Time (ms)", "Average Server Time (ms)",
        ])
        for name, values in sorted(SERVER_TIMINGS.items()):
            ordered = sorted(values)
            writer.writerow([
                name,
                len(ordered),
                round(ordered[0], 1),
                round(_percentile(ordered, 50), 1),
                round(_percentile(ordered, 95), 1),
                round(ordered[-1], 1),
                round(sum(ordered) / len(ordered), 1),
            ])
    logger.info(f"Server-side timing written to {path}")


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    csv_prefix = getattr(environment.parsed_options, "csv_prefix", None)
    if csv_prefix and SERVER_TIMINGS:
        _write_server_timing_csv(csv_prefix)
    logger.info("=" * 60)
    logger.info("BENCHMARK COMPLETE")
    logger.info("=" * 60)
    logger.info(f"Seed: {LOAD_SEED}  Anchor: {ANCHOR_DATE}")
    logger.info("Compare these results across different database configurations:")
    logger.info("  1. Single DB:     00-single-db/docker-compose.benchmark.yaml")
    logger.info("  2. Manual Shard:  01-manual-sharding/docker-compose.benchmark.yaml")
    logger.info("  3. Citus:         02-citus-sharding/docker-compose.benchmark.yaml")
    logger.info("  4. Lookup Table:  03-manual-sharding-lookup-table/docker-compose.benchmark.yaml")
    logger.info("=" * 60)
