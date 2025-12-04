import random
import sys
import uuid
from random import randint
from typing import Any

from utilities.commons.db_config import DbConfig
from utilities.commons.utilities import get_optimal_thread_count
from utilities.constants import DEFAULT_BATCH_SIZE, PRODUCT_LOG_INTERVAL, DEFAULT_USER_BATCH_SIZE_SINGLE, \
    DEFAULT_PRODUCT_FETCH_LIMIT_SINGLE, EXIT_FAILURE, ORDERS_VARIANCE, MIN_ITEMS_PER_ORDER, ITEMS_VARIANCE, \
    MIN_QUANTITY_PER_ITEM, MAX_QUANTITY_PER_ITEM, ORDER_LOG_INTERVAL
from utilities.database.generators.base import DataGenerator, DATA_GENERATOR
from utilities.generators.base_generator import generate_products_base


class SingleModeGenerator(DataGenerator):
    def __init__(self, db_config: DbConfig, logger_name: str = "dbsetup.data_generator"):
        super().__init__(logger_name, db_config)

    def generate_users(self, count: int, batch_size: int = DEFAULT_BATCH_SIZE) -> None:
        """Generate user records for 'single' mode with parallel processing."""
        self.logger.info(f"Generating {count} users ('single' mode) with parallel processing...")
        optimal_threads = get_optimal_thread_count(self.logger)
        total_generated = 0

        def process_user_batch(user_chunks: int) -> int:
            """Process a batch of users in a separate thread"""
            users = [DATA_GENERATOR.generate_user()[1:8] for _ in range(user_chunks)]
            self.db_manager.execute_batch(
                """
                INSERT INTO users (email, first_name, last_name, country, created_at, last_active, preferences)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                users
            )
            return user_chunks

        remaining = count

        while remaining > 0:
            current_batch_size = min(batch_size, remaining)
            chunk_size = current_batch_size // optimal_threads
            remainder = current_batch_size % optimal_threads
            if chunk_size == 0:
                chunk_size = current_batch_size
            chunks_to_process = [chunk_size] * optimal_threads
            chunks_to_process[0] += remainder
            total_generated += sum(self.thread_pool_executor.map(process_user_batch, chunks_to_process))
            remaining -= current_batch_size
            self.logger.info(f"-> Generated {total_generated}/{count} users...")

        self.logger.info(f"Finished generating users ('single' mode). Total generated: {total_generated}")

    def generate_orders(self, orders_per_user: int, items_per_order: int,
                        user_batch_size: int = DEFAULT_USER_BATCH_SIZE_SINGLE,
                        product_fetch_limit: int = DEFAULT_PRODUCT_FETCH_LIMIT_SINGLE) -> None:

        def process_single_user_with_connection(user_data: tuple[Any, ...], target_product_uuids: list[int]) -> tuple[int, int]:
            user_uuid, user_created_at = user_data
            orders_created_per_connection = 0
            items_created_per_connection = 0

            try:
                with self.db_manager.get_connection () as thread_conn:
                    with thread_conn.cursor() as thread_cur:
                        order = DATA_GENERATOR.generate_orders_for_user(user_uuid, user_created_at)
                        num_orders_for_this_user = randint(max(0, orders_per_user - ORDERS_VARIANCE),
                                                           orders_per_user + ORDERS_VARIANCE)

                        for _ in range(num_orders_for_this_user):
                            thread_cur.execute(
                                """
                                INSERT INTO orders (user_id, order_date, total_amount, status)
                                VALUES (%s, %s, %s, %s)
                                RETURNING order_id
                                """,
                                (user_uuid, order.order_date, order.total_amount, order.status)
                            )
                            result = thread_cur.fetchone()

                            if result:
                                order_uuid: uuid.UUID = result[0]
                                orders_created_per_connection += 1

                                num_items_for_this_order = randint(
                                    max(MIN_ITEMS_PER_ORDER, items_per_order - ORDERS_VARIANCE),
                                    items_per_order + ITEMS_VARIANCE)

                                order_items = random.sample(target_product_uuids, num_items_for_this_order)

                                for product_id in order_items:
                                    quantity = randint(MIN_QUANTITY_PER_ITEM, MAX_QUANTITY_PER_ITEM)
                                    thread_cur.execute(
                                        """
                                        INSERT INTO order_items (order_id, product_id, quantity)
                                        VALUES (%s, %s, %s)
                                        """,
                                        (order_uuid, product_id, quantity)
                                    )
                                    items_created_per_connection += 1

                return orders_created_per_connection, items_created_per_connection

            except Exception as order_e:
                self.logger.error(f"Error inserting order for user {user_uuid}: {order_e}")
                return 0, 0

        def get_products() -> tuple[int, list[int]]:
            try:
                user_count_result = self.db_manager.execute_query_fetch_one("SELECT COUNT(*) FROM users", ())
                total_user_count: int = user_count_result[0] if user_count_result else 0

                product_rows = self.db_manager.execute_query_fetch_all(
                    "SELECT product_id FROM products ORDER BY random() LIMIT %s",
                    (product_fetch_limit,)
                )
                product_uuids = [row[0] for row in product_rows]

                if not product_uuids:
                    self.logger.error("No products found in the database. Cannot generate order items.")
                    sys.exit(EXIT_FAILURE)

                self.logger.info(f"Fetched {len(product_uuids)} product UUIDs to use for items.")
                return total_user_count, product_uuids
            except Exception as e:
                self.logger.error(f"Failed to fetch product UUIDs: {e}")
                sys.exit(EXIT_FAILURE)

        self.logger.info(
            f"Generating orders (~{orders_per_user}/user) and items (~{items_per_order}/order) ('single' mode)...")
        total_orders_created = 0
        total_items_created = 0
        total_users_processed = 0

        self.logger.info("Fetching product UUIDs...")
        total_user_count, product_uuids = get_products()

        self.logger.info(f"Processing users in batches of {user_batch_size}...")
        user_offset = 0

        with self.db_manager.get_connection() as con:
            with con.cursor() as cur:
                while True:
                    try:
                        cur.execute(
                            "SELECT user_id, created_at FROM users ORDER BY created_at LIMIT %s OFFSET %s",
                            (user_batch_size, user_offset)
                        )
                        user_batch = cur.fetchall()

                        if not user_batch:
                            if user_offset == total_user_count:
                                self.logger.info(f"Order -> User processing completed.")
                                break
                            else:
                                self.logger.error(f"No more users found.")
                                sys.exit(EXIT_FAILURE)

                        results = list(self.thread_pool_executor.map(
                            lambda user: process_single_user_with_connection(user, product_uuids),
                            user_batch))

                        for orders_created, items_created in results:
                            total_orders_created += orders_created
                            total_items_created += items_created
                            total_users_processed += 1

                        user_offset += len(user_batch)

                        if total_orders_created > 0 and total_orders_created % ORDER_LOG_INTERVAL == 0:
                            self.logger.info(
                                f"-> Generated {total_orders_created} orders and {total_items_created} items...")

                    except Exception as e:
                        self.logger.error(f"Error fetching user batch: {e}")
                        break

            self.logger.info(f"Finished generating orders ('single-shard' mode). Processed {total_users_processed} users.")
            self.logger.info(f"Total orders created: {total_orders_created}, Total items created: {total_items_created}")

    def generate_products(self, count: int) -> None:
        def product_generator() -> Any:
            return DATA_GENERATOR.generate_product()

        def insert_product(product: Any) -> None:
            self.db_manager.execute_query(
                """
                INSERT INTO products (name, description, price, category, technical_specs)
                VALUES (%s, %s, %s, %s, %s)""",
                (
                    product.name,
                    product.description,
                    product.price,
                    product.category,
                    product.technical_specs)
            )

        generate_products_base(product_generator, insert_product, count, self.logger, PRODUCT_LOG_INTERVAL, "single")
