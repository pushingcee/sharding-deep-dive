import uuid
from datetime import date, datetime

from psycopg import Connection, connect

from utilities.config import DbConfig
from utilities.connection_manager import connect_to_shards, close_shard_connections
from utilities.constants import (
    DEFAULT_BATCH_SIZE,
    DEFAULT_PRODUCT_FETCH_LIMIT,
    DEFAULT_USER_BATCH_SIZE,
    ITEMS_VARIANCE,
    MIN_ITEMS_PER_ORDER,
    MIN_QUANTITY_PER_ITEM,
    MAX_QUANTITY_PER_ITEM,
    ORDERS_VARIANCE,
)
from utilities.data_factory import User
from utilities.generators.base import BaseGenerator, get_factory

UserRow = tuple[uuid.UUID, str, str, str, str, datetime, date | None, str]


def user_to_row(user: User) -> UserRow:
    return (
        user.user_uuid,
        user.email,
        user.first_name,
        user.last_name,
        user.country,
        user.created_at,
        user.last_active,
        user.preferences,
    )


def group_users_by_shard(users: list[User]) -> dict[int, list[UserRow]]:
    users_by_shard: dict[int, list[UserRow]] = {}
    for user in users:
        shard_index = user.target_shard_index
        if shard_index is None:
            raise ValueError("target_shard_index must be set in sharded mode")
        users_by_shard.setdefault(shard_index, []).append(user_to_row(user))
    return users_by_shard


class ShardedGenerator(BaseGenerator):
    """Data generator for sharded database mode with multiple PostgreSQL instances."""

    INSERT_USERS_SQL = (
        "INSERT INTO users "
        "(user_id, email, first_name, last_name, country, created_at, last_active, preferences) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"
    )

    def __init__(self, shard_configs: tuple[DbConfig, ...], logger_name: str = "dbsetup.data_generator") -> None:
        super().__init__(logger_name)
        self.shard_configs = shard_configs

    def generate_users(self, count: int, batch_size: int = DEFAULT_BATCH_SIZE) -> None:
        self.logger.info(f"Generating {count} users ('sharded' mode) with batch inserts...")

        def process_user_batch(chunk_count: int) -> int:
            factory = get_factory()
            users = [factory.generate_user(sharded=True) for _ in range(chunk_count)]
            users_by_shard = group_users_by_shard(users)
            batch_generated = 0
            for shard_index, user_rows in users_by_shard.items():
                # Each worker opens its own short-lived connection so shard
                # writes from different threads never serialize on a shared
                # connection.
                with connect(self.shard_configs[shard_index].conninfo) as conn:
                    with conn.cursor() as cur:
                        cur.executemany(self.INSERT_USERS_SQL, user_rows)
                    conn.commit()
                batch_generated += len(user_rows)
            return batch_generated

        total = self.run_user_batches(count, batch_size, process_user_batch)
        self.logger.info(f"Finished generating users ('sharded' mode). Total generated: {total}")

    def generate_products(self, count: int) -> None:
        """Products are a reference table: the SAME rows are replicated to
        every shard (AnalyticsFanOut relies on identical catalogs). Generate
        once, then batch-insert per shard in one transaction each — a failed
        shard aborts the run instead of leaving catalogs diverged."""
        self.logger.info(f"Generating {count} products ('sharded' mode)...")
        factory = get_factory()
        rows = [
            (p.product_uuid, p.name, p.description, p.price, p.category, p.technical_specs)
            for p in (factory.generate_product() for _ in range(count))
        ]
        for shard_index, shard_config in enumerate(self.shard_configs):
            with connect(shard_config.conninfo) as conn:
                with conn.cursor() as cur:
                    cur.executemany(
                        "INSERT INTO products "
                        "(product_id, name, description, price, category, technical_specs) "
                        "VALUES (%s, %s, %s, %s, %s, %s)",
                        rows,
                    )
                conn.commit()
            self.logger.info(f"Replicated {len(rows)} products to Shard {shard_index + 1}.")
        self.logger.info(f"Finished generating products ('sharded' mode). Total generated: {len(rows)}")

    def generate_orders(
        self,
        orders_per_user: int,
        items_per_order: int,
        user_batch_size: int = DEFAULT_USER_BATCH_SIZE,
        product_fetch_limit: int = DEFAULT_PRODUCT_FETCH_LIMIT,
    ) -> None:
        self.logger.info(
            f"Generating orders (~{orders_per_user}/user) and items (~{items_per_order}/order) "
            f"('sharded' mode) with batch inserts..."
        )
        total_orders_created = 0
        total_items_created = 0
        total_users_processed = 0

        shard_connections = connect_to_shards(self.shard_configs, self.logger)
        try:
            product_uuids = self._fetch_product_uuids(shard_connections[0], product_fetch_limit)

            def process_user_orders_batch(
                user_batch_data: tuple[int, list[tuple[uuid.UUID, datetime]]],
            ) -> tuple[int, int, int]:
                shard_index, user_batch = user_batch_data
                factory = get_factory()
                orders_data: list[tuple[uuid.UUID, uuid.UUID, datetime, float, str]] = []
                items_data: list[tuple[uuid.UUID, uuid.UUID, int]] = []

                for user_uuid, user_created_at in user_batch:
                    num_orders = factory.rng.randint(
                        max(0, orders_per_user - ORDERS_VARIANCE),
                        orders_per_user + ORDERS_VARIANCE,
                    )
                    for _ in range(num_orders):
                        order = factory.generate_orders_for_user(user_uuid, user_created_at)
                        order_uuid = uuid.uuid4()
                        orders_data.append(
                            (order_uuid, user_uuid, order.order_date, order.total_amount, order.status)
                        )
                        num_items = min(
                            factory.rng.randint(
                                max(MIN_ITEMS_PER_ORDER, items_per_order - ITEMS_VARIANCE),
                                items_per_order + ITEMS_VARIANCE,
                            ),
                            len(product_uuids),
                        )
                        for product_uuid in factory.rng.sample(product_uuids, num_items):
                            quantity = factory.rng.randint(MIN_QUANTITY_PER_ITEM, MAX_QUANTITY_PER_ITEM)
                            items_data.append((order_uuid, product_uuid, quantity))

                with connect(self.shard_configs[shard_index].conninfo) as thread_conn:
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
                return len(orders_data), len(items_data), len(user_batch)

            self.logger.info(f"Processing users from each shard in keyset-paginated batches of {user_batch_size}...")

            for s_idx, conn in enumerate(shard_connections):
                self.logger.info(f"--- Processing Shard {s_idx + 1} ---")
                shard_orders = 0
                shard_items = 0
                shard_users = 0
                cursor_key: tuple[datetime, uuid.UUID] | None = None

                while True:
                    with conn.cursor() as cur:
                        # Keyset pagination on (created_at, user_id): stable
                        # page boundaries (created_at alone is not unique) and
                        # no O(n²) OFFSET rescans.
                        if cursor_key is None:
                            cur.execute(
                                "SELECT user_id, created_at FROM users "
                                "ORDER BY created_at, user_id LIMIT %s",
                                (user_batch_size,),
                            )
                        else:
                            cur.execute(
                                "SELECT user_id, created_at FROM users "
                                "WHERE (created_at, user_id) > (%s, %s) "
                                "ORDER BY created_at, user_id LIMIT %s",
                                (cursor_key[0], cursor_key[1], user_batch_size),
                            )
                        user_batch: list[tuple[uuid.UUID, datetime]] = cur.fetchall()

                    if not user_batch:
                        self.logger.info(f"[Shard {s_idx + 1}] No more users found.")
                        break

                    last_user_id, last_created_at = user_batch[-1]
                    cursor_key = (last_created_at, last_user_id)

                    chunk_size = max(1, len(user_batch) // self.thread_count)
                    user_chunks = [user_batch[i:i + chunk_size] for i in range(0, len(user_batch), chunk_size)]
                    batch_data = [(s_idx, chunk) for chunk in user_chunks if chunk]
                    batch_results = list(self.thread_pool_executor.map(process_user_orders_batch, batch_data))

                    for orders_created, items_created, users_processed in batch_results:
                        shard_orders += orders_created
                        shard_items += items_created
                        shard_users += users_processed

                    self.logger.info(
                        f"[Shard {s_idx + 1}] Batch processed. "
                        f"Orders so far: {shard_orders}, Items so far: {shard_items}"
                    )

                total_orders_created += shard_orders
                total_items_created += shard_items
                total_users_processed += shard_users
                self.logger.info(
                    f"[Shard {s_idx + 1}] Completed. "
                    f"Orders: {shard_orders}, Items: {shard_items}, Users: {shard_users}"
                )
        finally:
            close_shard_connections(shard_connections, self.logger)

        self.logger.info(f"Finished generating orders ('sharded' mode). Processed {total_users_processed} users.")
        self.logger.info(f"Total orders created: {total_orders_created}, Total items created: {total_items_created}")

    def _fetch_product_uuids(self, conn: Connection, product_fetch_limit: int) -> list[uuid.UUID]:
        self.logger.info("Fetching product UUIDs (from Shard 1 — products are replicated)...")
        with conn.cursor() as cur:
            cur.execute("SELECT product_id FROM products ORDER BY random() LIMIT %s", (product_fetch_limit,))
            product_uuids = [row[0] for row in cur.fetchall()]
        if not product_uuids:
            raise RuntimeError("No product UUIDs found in Shard 1. Cannot generate order items.")
        self.logger.info(f"Fetched {len(product_uuids)} product UUIDs to use for items.")
        return product_uuids
