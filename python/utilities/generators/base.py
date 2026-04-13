import logging
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Self

from utilities.config import DbConfig
from utilities.connection_manager import DatabaseManager
from utilities.constants import (
    DEFAULT_USER_BATCH_SIZE_SINGLE,
    DEFAULT_PRODUCT_FETCH_LIMIT_SINGLE,
    PRODUCT_LOG_INTERVAL,
)
from utilities.data_factory import DataFactory, Product
from utilities.shard_utils import get_optimal_thread_count

DATA_GENERATOR = DataFactory()


def generate_products_base(
    product_generator_func: Callable[[], Product],
    insert_func: Callable[[Product], None],
    count: int,
    logger: logging.Logger,
    log_interval: int = PRODUCT_LOG_INTERVAL,
    mode_name: str = "unknown",
) -> int:
    logger.info(f"Generating {count} products ('{mode_name}' mode)...")
    generated_count = 0
    for _ in range(count):
        product = product_generator_func()
        try:
            insert_func(product)
            generated_count += 1
            if generated_count % log_interval == 0:
                logger.info(f"-> Generated {generated_count} products...")
        except Exception as e:
            logger.error(f"Error inserting product: {e}")
    logger.info(f"Finished generating products for '{mode_name}' mode. Total generated: {generated_count}")
    return generated_count


class BaseGenerator(ABC):

    def __init__(self, logger_name: str, db_config: DbConfig) -> None:
        self.db_config = db_config
        self.logger = logging.getLogger(logger_name)
        self.db_manager: DatabaseManager = DatabaseManager(db_config=db_config)
        self.thread_pool_executor = ThreadPoolExecutor(max_workers=get_optimal_thread_count(self.logger))

    def __enter__(self) -> Self:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.thread_pool_executor.shutdown(wait=True)

    @abstractmethod
    def generate_users(self, count: int) -> None:
        pass

    @abstractmethod
    def generate_orders(
        self,
        orders_per_user: int,
        items_per_order: int,
        user_batch_size: int = DEFAULT_USER_BATCH_SIZE_SINGLE,
        product_fetch_limit: int = DEFAULT_PRODUCT_FETCH_LIMIT_SINGLE,
    ) -> None:
        pass

    @abstractmethod
    def generate_products(self, count: int) -> None:
        pass
