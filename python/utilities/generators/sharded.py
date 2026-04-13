import random
import sys
import uuid
from datetime import datetime

from psycopg import Connection, connect

from utilities.config import DbConfig
from utilities.connection_manager import connect_to_shards, close_shard_connections
from utilities.constants import (
    DEFAULT_BATCH_SIZE,
    DEFAULT_PRODUCT_FETCH_LIMIT_SHARDED,
    DEFAULT_USER_BATCH_SIZE_SHARDED,
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


class ShardedGenerator(BaseGenerator):
    """Data generator for sharded database mode with multiple PostgreSQL instances."""

    def __init__(self, shard_configs: tuple[DbConfig, ...], logger_name: str = "dbsetup.data_generator") -> None:
        super().__init__(logger_name, shard_configs[0])
        self.shard_configs = shard_configs

    def generate_users(self, count: int, batch_size: int = DEFAULT_BATCH_SIZE) -> None:
        self.logger.info(f"Generating {count} users ('sharded' mode) with batch inserts...")
        optimal_threads = get_optimal_thread_count(self.logger)
        total_generated = 0

        def process_user_batch(user_chunks: int) -> int:
            batch_generated = 0
            try:
                users = [DATA_GENERATOR.generate_user(sharded=True) for _ in range(user_chunks)]
                users_by_shard: dict[int, list[tuple[uuid.UUID, str, str, str, str, datetime, object, str]]] = {}
                for user in users:
                    shard_index = user.target_shard_index
                    assert shard_index is not None, "target_shard_index must be set in sharded mode"
                    if shard_index not in users_by_shard:
                        users_by_shard[shard_index] = []
                    users_by_shard[shard_index].append((
                        user.user_uuid,
                        user.email,
                        user.first_name,
                        user.last_name,
                        user.country,
                        user.created_at,
                        user.last_active,
                        user.preferences,
                    ))
                for shard_index, user_data_list in users_by_shard.items():
                    shard_config = self.shard_configs[shard_index]
                    try:
                        with connect(str(shard_config), autocommit=False) as conn:
                            with conn.cursor() as cur:
                                cur.executemany(
                                    "INSERT INTO users "
                                    "(user_id, email, first_name, last_name, country, created_at, last_active, preferences) "
                                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                                    user_data_list,
                                )
                            conn.commit()
                            batch_generated += len(user_data_list)
                    except Exception as e:
                        self.logger.error(f"Error inserting users to shard {shard_index + 1}: {e}")
                return batch_generated
            except Exception as e:
                self.logger.error(f"Error in sharded user batch processing: {e}")
                return 0

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

        self.logger.info(f"Finished generating users ('sharded' mode). Total generated: {total_generated}")

    def generate_products(self, count: int) -> None:
        shard_connections: list[Connection] = connect_to_shards(self.shard_configs, self.logger)

        def product_generator() -> Product:
            return DATA_GENERATOR.generate_product()

        def insert_product(product: Product) -> None:
            for s_idx, conn in enumerate(shard_connections):
                try:
                    with conn.cursor() as cur:
                        cur.execute(
                            "INSERT INTO products "
                            "(product_id, name, description, price, category, technical_specs) "
                            "VALUES (%s, %s, %s, %s, %s, %s)",
                            (
                                product.product_uuid,
                                product.name,
                                product.description,
                                product.price,
                                product.category,
                                product.technical_specs,
                            ),
                        )
                except Exception as e:
                    self.logger.error(f"Failed to insert product {product.product_uuid} into Shard {s_idx + 1}: {e}")
                    sys.exit(EXIT_FAILURE)

        try:
            generate_products_base(product_generator, insert_product, count, self.logger, PRODUCT_LOG_INTERVAL, "sharded")
        finally:
            close_shard_connections(shard_connections, self.logger)

    def generate_orders(
        self,
        orders_per_user: int,
        items_per_order: int,
        user_batch_size: int = DEFAULT_USER_BATCH_SIZE_SHARDED,
        product_fetch_limit: int = DEFAULT_PRODUCT_FETCH_LIMIT_SHARDED,
    ) -> None:
        self.logger.info(
            f"Generating orders (~{orders_per_user}/user) and items (~{items_per_order}/order) "
            f"('sharded' mode) with batch inserts..."
        )
        optimal_threads = get_optimal_thread_count(self.logger)
        total_orders_created = 0
        total_items_created = 0
        total_users_processed = 0

        shard_connections: list[Connection] = connect_to_shards(self.shard_configs, self.logger)

        product_uuids: list[uuid.UUID] = []
        self.logger.info("Fetching product UUIDs (from Shard 1, assuming replication)...")
        try:
            with shard_connections[0].cursor() as cur:
                cur.execute("SELECT product_id FROM products ORDER BY random() LIMIT %s", (product_fetch_limit,))
                product_uuids = [row[0] for row in cur.fetchall()]
                if not product_uuids:
                    self.logger.error("No product UUIDs found in Shard 1. Cannot generate order items.")
                    close_shard_connections(shard_connections, self.logger)
                    sys.exit(EXIT_FAILURE)
                self.logger.info(f"Fetched {len(product_uuids)} product UUIDs to use for items.")
        except Exception as e:
            self.logger.error(f"Failed to fetch product UUIDs from Shard 1: {e}")
            close_shard_connections(shard_connections, self.logger)
            sys.exit(EXIT_FAILURE)

        def process_user_orders_batch(
            user_batch_data: tuple[int, list[tuple[uuid.UUID, datetime]]],
        ) -> tuple[int, int, int]:
            shard_index, user_batch = user_batch_data
            batch_orders = 0
            batch_items = 0
            batch_users = len(user_batch)
            shard_config = self.shard_configs[shard_index]

            try:
                with connect(str(shard_config), autocommit=False) as thread_conn:
                    orders_data: list[tuple[uuid.UUID, uuid.UUID, datetime, float, str]] = []
                    items_data: list[tuple[uuid.UUID, uuid.UUID, int]] = []

                    for user_uuid, user_created_at in user_batch:
                        num_orders = random.randint(
                            max(0, orders_per_user - ORDERS_VARIANCE),
                            orders_per_user + ORDERS_VARIANCE,
                        )
                        for _ in range(num_orders):
                            order = DATA_GENERATOR.generate_orders_for_user(user_uuid, user_created_at)
                            order_uuid = uuid.uuid4()
                            orders_data.append((order_uuid, user_uuid, order.order_date, order.total_amount, order.status))
                            batch_orders += 1

                            num_items = min(
                                random.randint(
                                    max(MIN_ITEMS_PER_ORDER, items_per_order - ITEMS_VARIANCE),
                                    items_per_order + ITEMS_VARIANCE,
                                ),
                                len(product_uuids),
                            )
                            for product_uuid in random.sample(product_uuids, num_items):
                                quantity = random.randint(MIN_QUANTITY_PER_ITEM, MAX_QUANTITY_PER_ITEM)
                                items_data.append((order_uuid, product_uuid, quantity))
                                batch_items += 1

                    with thread_conn.cursor() as cur:
                        if orders_data:
                            cur.executemany(
                                "INSERT INTO orders (order_id, user_id, order_date, total_amount, status) "
                                "VALUES (%s, %s, %s, %s, %s)",
                                orders_data,
                            )
                        if items_data:
                            cur.executemany(
                                "INSERT INTO order_items (order_id, product_id, quantity) VALUES (%s, %s, %s)",
                                items_data,
                            )
                    thread_conn.commit()
                    return batch_orders, batch_items, batch_users
            except Exception as e:
                self.logger.error(f"Error in threaded order processing for shard {shard_index + 1}: {e}")
                return 0, 0, 0

        self.logger.info(f"Processing users from each shard in batches of {user_batch_size}...")

        for s_idx, conn in enumerate(shard_connections):
            self.logger.info(f"--- Processing Shard {s_idx + 1} ---")
            user_offset = 0
            shard_orders = 0
            shard_items = 0
            shard_users = 0

            while True:
                self.logger.debug(f"[Shard {s_idx + 1}] Fetching user batch (offset {user_offset})...")
                try:
                    with conn.cursor() as cur:
                        cur.execute(
                            "SELECT user_id, created_at FROM users ORDER BY created_at LIMIT %s OFFSET %s",
                            (user_batch_size, user_offset),
                        )
                        user_batch: list[tuple[uuid.UUID, datetime]] = cur.fetchall()

                        if not user_batch:
                            self.logger.info(f"[Shard {s_idx + 1}] No more users found.")
                            break

                        self.logger.info(
                            f"[Shard {s_idx + 1}] Processing batch of {len(user_batch)} users "
                            f"(offset {user_offset}) with {optimal_threads} threads..."
                        )
                        chunk_size = max(1, len(user_batch) // optimal_threads)
                        user_chunks = [user_batch[i:i + chunk_size] for i in range(0, len(user_batch), chunk_size)]
                        batch_data = [(s_idx, chunk) for chunk in user_chunks if chunk]
                        batch_results = list(self.thread_pool_executor.map(process_user_orders_batch, batch_data))

                        for orders_created, items_created, users_processed in batch_results:
                            shard_orders += orders_created
                            shard_items += items_created
                            shard_users += users_processed

                        user_offset += len(user_batch)
                        self.logger.info(
                            f"[Shard {s_idx + 1}] Batch processed. "
                            f"Orders so far: {shard_orders}, Items so far: {shard_items}"
                        )
                except Exception as e:
                    self.logger.error(
                        f"[Shard {s_idx + 1}] Unexpected error processing user batch (offset {user_offset}): {e}"
                    )
                    close_shard_connections(shard_connections, self.logger)
                    sys.exit(EXIT_FAILURE)

            total_orders_created += shard_orders
            total_items_created += shard_items
            total_users_processed += shard_users
            self.logger.info(
                f"[Shard {s_idx + 1}] Completed. "
                f"Orders: {shard_orders}, Items: {shard_items}, Users: {shard_users}"
            )

        close_shard_connections(shard_connections, self.logger)
        self.logger.info(f"Finished generating orders ('sharded' mode). Processed {total_users_processed} users.")
        self.logger.info(f"Total orders created: {total_orders_created}, Total items created: {total_items_created}")
