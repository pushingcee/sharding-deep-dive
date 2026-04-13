import random
import sys
import uuid
from datetime import datetime
from random import randint
from typing import Any

from psycopg.sql import SQL, Placeholder

from utilities.config import DbConfig
from utilities.constants import (
    DEFAULT_BATCH_SIZE,
    DEFAULT_PRODUCT_FETCH_LIMIT_SINGLE,
    DEFAULT_USER_BATCH_SIZE_SINGLE,
    EXIT_FAILURE,
    ITEMS_VARIANCE,
    MIN_ITEMS_PER_ORDER,
    MIN_QUANTITY_PER_ITEM,
    MAX_QUANTITY_PER_ITEM,
    ORDERS_VARIANCE,
    PRODUCT_LOG_INTERVAL,
)
from utilities.data_factory import Product
from utilities.generators.base import BaseGenerator, DATA_GENERATOR, generate_products_base
from utilities.shard_utils import get_optimal_thread_count


class SingleGenerator(BaseGenerator):
    def __init__(self, db_config: DbConfig, logger_name: str = "dbsetup.data_generator") -> None:
        super().__init__(logger_name, db_config)

    def generate_users(self, count: int, batch_size: int = DEFAULT_BATCH_SIZE) -> None:
        self.logger.info(f"Generating {count} users ('single' mode) with parallel processing...")
        optimal_threads = get_optimal_thread_count(self.logger)
        total_generated = 0

        def process_user_batch(user_chunks: int) -> int:
            users = [DATA_GENERATOR.generate_user()[1:8] for _ in range(user_chunks)]
            self.db_manager.execute_batch(
                """
                INSERT INTO users (email, first_name, last_name, country, created_at, last_active, preferences)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                users,
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

    def generate_orders(
        self,
        orders_per_user: int,
        items_per_order: int,
        user_batch_size: int = DEFAULT_USER_BATCH_SIZE_SINGLE,
        product_fetch_limit: int = DEFAULT_PRODUCT_FETCH_LIMIT_SINGLE,
    ) -> None:
        self.logger.info(
            f"Generating orders (~{orders_per_user}/user) and items (~{items_per_order}/order) "
            f"('single' mode) with batch inserts..."
        )

        def get_products() -> tuple[int, list[uuid.UUID]]:
            try:
                user_count_result = self.db_manager.execute_query_fetch_one("SELECT COUNT(*) FROM users", ())
                total_user_count: int = user_count_result[0] if user_count_result else 0
                product_rows = self.db_manager.execute_query_fetch_all(
                    "SELECT product_id FROM products ORDER BY random() LIMIT %s",
                    (product_fetch_limit,),
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

        def process_user_batch_optimized(
            user_batch: list[tuple[uuid.UUID, datetime]],
            product_uuids: list[uuid.UUID],
        ) -> tuple[int, int]:
            # PostgreSQL parameter limit is 65535. With 4 params per order, max ~16000 orders per INSERT.
            MAX_ORDERS_PER_INSERT = 16000
            orders_data: list[tuple[uuid.UUID, datetime, float, str]] = []
            items_per_order_list: list[tuple[list[uuid.UUID], list[int]]] = []

            for user_uuid, user_created_at in user_batch:
                num_orders = randint(
                    max(0, orders_per_user - ORDERS_VARIANCE),
                    orders_per_user + ORDERS_VARIANCE,
                )
                for _ in range(num_orders):
                    order = DATA_GENERATOR.generate_orders_for_user(user_uuid, user_created_at)
                    orders_data.append((user_uuid, order.order_date, order.total_amount, order.status))
                    num_items = min(
                        randint(
                            max(MIN_ITEMS_PER_ORDER, items_per_order - ITEMS_VARIANCE),
                            items_per_order + ITEMS_VARIANCE,
                        ),
                        len(product_uuids),
                    )
                    selected_products = random.sample(product_uuids, num_items)
                    quantities = [randint(MIN_QUANTITY_PER_ITEM, MAX_QUANTITY_PER_ITEM) for _ in range(num_items)]
                    items_per_order_list.append((selected_products, quantities))

            if not orders_data:
                return 0, 0

            try:
                with self.db_manager.get_connection() as conn:
                    with conn.cursor() as cur:
                        all_order_ids: list[uuid.UUID] = []
                        for chunk_start in range(0, len(orders_data), MAX_ORDERS_PER_INSERT):
                            orders_chunk = orders_data[chunk_start:chunk_start + MAX_ORDERS_PER_INSERT]
                            values_template = SQL('({})').format(SQL(',').join([Placeholder()] * 4))
                            values_clause = SQL(',').join([values_template] * len(orders_chunk))
                            query = SQL(
                                "INSERT INTO orders (user_id, order_date, total_amount, status) "
                                "VALUES {} RETURNING order_id"
                            ).format(values_clause)
                            flat_params = [item for row in orders_chunk for item in row]
                            cur.execute(query, flat_params)
                            all_order_ids.extend(row[0] for row in cur.fetchall())

                        items_data: list[tuple[uuid.UUID, uuid.UUID, int]] = []
                        for order_id, (products, quantities) in zip(all_order_ids, items_per_order_list):
                            for product_id, quantity in zip(products, quantities):
                                items_data.append((order_id, product_id, quantity))

                        if items_data:
                            cur.executemany(
                                "INSERT INTO order_items (order_id, product_id, quantity) VALUES (%s, %s, %s)",
                                items_data,
                            )
                        conn.commit()
                        return len(all_order_ids), len(items_data)
            except Exception as e:
                self.logger.error(f"Error in batch order processing: {e}")
                return 0, 0

        total_orders_created = 0
        total_items_created = 0
        total_users_processed = 0

        self.logger.info("Fetching product UUIDs...")
        total_user_count, product_uuids = get_products()

        processing_batch_size = min(user_batch_size, 5000)
        self.logger.info(f"Processing users in batches of {processing_batch_size}...")
        user_offset = 0

        with self.db_manager.get_connection() as con:
            with con.cursor() as cur:
                while True:
                    try:
                        cur.execute(
                            "SELECT user_id, created_at FROM users ORDER BY created_at LIMIT %s OFFSET %s",
                            (user_batch_size, user_offset),
                        )
                        user_batch: list[tuple[uuid.UUID, datetime]] = cur.fetchall()

                        if not user_batch:
                            self.logger.info("Order -> User processing completed.")
                            break

                        optimal_threads = get_optimal_thread_count(self.logger)
                        chunk_size = max(1, len(user_batch) // optimal_threads)
                        user_chunks = [
                            user_batch[i:i + chunk_size] for i in range(0, len(user_batch), chunk_size)
                        ]

                        def process_chunk(
                            chunk: list[tuple[uuid.UUID, datetime]],
                        ) -> tuple[int, int]:
                            return process_user_batch_optimized(chunk, product_uuids)

                        results = list(self.thread_pool_executor.map(process_chunk, user_chunks))

                        for orders_created, items_created in results:
                            total_orders_created += orders_created
                            total_items_created += items_created

                        total_users_processed += len(user_batch)
                        user_offset += len(user_batch)
                        self.logger.info(
                            f"-> Processed {total_users_processed} users, "
                            f"{total_orders_created} orders, {total_items_created} items..."
                        )
                    except Exception as e:
                        self.logger.error(f"Error fetching user batch: {e}")
                        break

        self.logger.info(f"Finished generating orders ('single' mode). Processed {total_users_processed} users.")
        self.logger.info(f"Total orders created: {total_orders_created}, Total items created: {total_items_created}")

    def generate_products(self, count: int) -> None:
        def product_generator() -> Product:
            return DATA_GENERATOR.generate_product()

        def insert_product(product: Product) -> None:
            self.db_manager.execute_query(
                "INSERT INTO products (name, description, price, category, technical_specs) "
                "VALUES (%s, %s, %s, %s, %s)",
                (product.name, product.description, product.price, product.category, product.technical_specs),
            )

        generate_products_base(product_generator, insert_product, count, self.logger, PRODUCT_LOG_INTERVAL, "single")
