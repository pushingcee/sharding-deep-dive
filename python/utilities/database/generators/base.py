import logging
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from utilities.commons.data_generator import DataGenerator as CommonDataGenerator
from utilities.commons.db_config import DbConfig
from utilities.commons.utilities import get_optimal_thread_count
from utilities.constants import DEFAULT_USER_BATCH_SIZE_SINGLE, DEFAULT_PRODUCT_FETCH_LIMIT_SINGLE
from utilities.database.database_connection_manager import DatabaseManager

DATA_GENERATOR = CommonDataGenerator()


class DataGenerator(ABC):

    def __init__(self, logger_name: str, db_config: DbConfig):
        self.db_config = db_config
        self.logger = logging.getLogger(logger_name)
        self.db_manager: DatabaseManager = DatabaseManager(db_config=db_config)
        self.thread_pool_executor = ThreadPoolExecutor(max_workers=get_optimal_thread_count(self.logger))

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> bool:
        self.thread_pool_executor.shutdown(wait=True)
        return False

    def __enter__(self) -> 'DataGenerator':
        return self

    @abstractmethod
    def generate_users(self, count: int) -> None:
        pass

    @abstractmethod
    def generate_orders(self, orders_per_user: int, items_per_order: int,
                        user_batch_size: int = DEFAULT_USER_BATCH_SIZE_SINGLE,
                        product_fetch_limit: int = DEFAULT_PRODUCT_FETCH_LIMIT_SINGLE):
        pass

    @abstractmethod
    def generate_products(self, count: int) -> None:
        pass
