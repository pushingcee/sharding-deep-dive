import logging
import threading
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Self

from utilities.constants import (
    DEFAULT_PRODUCT_FETCH_LIMIT,
    DEFAULT_USER_BATCH_SIZE,
)
from utilities.data_factory import DataFactory
from utilities.shard_utils import get_optimal_thread_count

_thread_local = threading.local()


def get_factory() -> DataFactory:
    """Per-thread DataFactory.

    Faker and random.Random keep mutable state and are not thread-safe, so
    each worker thread lazily gets its own instance instead of all threads
    sharing one module-level factory.
    """
    factory: DataFactory | None = getattr(_thread_local, "factory", None)
    if factory is None:
        factory = DataFactory()
        _thread_local.factory = factory
    return factory


class BaseGenerator(ABC):

    def __init__(self, logger_name: str) -> None:
        self.logger = logging.getLogger(logger_name)
        self.thread_count = get_optimal_thread_count(self.logger)
        self.thread_pool_executor = ThreadPoolExecutor(max_workers=self.thread_count)

    def __enter__(self) -> Self:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.thread_pool_executor.shutdown(wait=True)

    def run_user_batches(self, count: int, batch_size: int, process_chunk: Callable[[int], int]) -> int:
        """Split `count` into batches and fan each batch out over the thread
        pool. `process_chunk` receives a chunk size and returns the number of
        rows it wrote.

        Worker exceptions propagate: a failed seed run must abort loudly, not
        under-report totals — partially seeded shards silently invalidate
        every benchmark that runs on top of them.
        """
        total_generated = 0
        remaining = count
        while remaining > 0:
            current_batch_size = min(batch_size, remaining)
            chunk_size, remainder = divmod(current_batch_size, self.thread_count)
            if chunk_size == 0:
                chunks = [current_batch_size]
            else:
                chunks = [chunk_size] * self.thread_count
                chunks[0] += remainder
            total_generated += sum(self.thread_pool_executor.map(process_chunk, chunks))
            remaining -= current_batch_size
            self.logger.info(f"-> Generated {total_generated}/{count} users...")
        return total_generated

    @abstractmethod
    def generate_users(self, count: int) -> None:
        pass

    @abstractmethod
    def generate_orders(
        self,
        orders_per_user: int,
        items_per_order: int,
        user_batch_size: int = DEFAULT_USER_BATCH_SIZE,
        product_fetch_limit: int = DEFAULT_PRODUCT_FETCH_LIMIT,
    ) -> None:
        pass

    @abstractmethod
    def generate_products(self, count: int) -> None:
        pass
