import uuid
from datetime import date, datetime

from psycopg.sql import SQL, Placeholder

from utilities.config import DbConfig
from utilities.connection_manager import DatabaseManager
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
from utilities.generators.base import BaseGenerator, get_factory


class SingleGenerator(BaseGenerator):
    def __init__(self, db_config: DbConfig, logger_name: str = "dbsetup.data_generator") -> None:
        super().__init__(logger_name)
        self.db_config = db_config
        self.db_manager = DatabaseManager(db_config=db_config)

    def generate_users(self, count: int, batch_size: int = DEFAULT_BATCH_SIZE) -> None:
        self.logger.info(f"Generating {count} users ('single' mode) with parallel batch inserts...")

        def process_user_batch(chunk_count: int) -> int:
            factory = get_factory()
            rows: list[tuple[str, str, str, str, datetime, date | None, str]] = []
            for _ in range(chunk_count):
                user = factory.generate_user()
                # Single mode lets the DB assign user_id (DEFAULT gen_random_uuid()).
                rows.append((
                    user.email,
                    user.first_name,
                    user.last_name,
                    user.country,
                    user.created_at,
                    user.last_active,
                    user.preferences,
                ))
            self.db_manager.execute_batch(
                """
                INSERT INTO users (email, first_name, last_name, country, created_at, last_active, preferences)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                rows,
            )
            return chunk_count

        total = self.run_user_batches(count, batch_size, process_user_batch)
        self.logger.info(f"Finished generating users ('single' mode). Total generated: {total}")

    def generate_orders(
        self,
        orders_per_user: int,
        items_per_order: int,
        user_batch_size: int = DEFAULT_USER_BATCH_SIZE,
        product_fetch_limit: int = DEFAULT_PRODUCT_FETCH_LIMIT,
    ) -> None:
        self.logger.info(
            f"Generating orders (~{orders_per_user}/user) and items (~{items_per_order}/order) "
            f"('single' mode) with batch inserts..."
        )

        product_uuids = self._fetch_product_uuids(product_fetch_limit)

        def process_user_batch_optimized(
            user_batch: list[tuple[uuid.UUID, datetime]],
        ) -> tuple[int, int]:
            factory = get_factory()
            # PostgreSQL parameter limit is 65535. With 4 params per order, max ~16000 orders per INSERT.
            MAX_ORDERS_PER_INSERT = 16000
            orders_data: list[tuple[uuid.UUID, datetime, float, str]] = []
            items_per_order_list: list[tuple[list[uuid.UUID], list[int]]] = []

            for user_uuid, user_created_at in user_batch:
                num_orders = factory.rng.randint(
                    max(0, orders_per_user - ORDERS_VARIANCE),
                    orders_per_user + ORDERS_VARIANCE,
                )
                for _ in range(num_orders):
                    order = factory.generate_orders_for_user(user_uuid, user_created_at)
                    orders_data.append((user_uuid, order.order_date, order.total_amount, order.status))
                    num_items = min(
                        factory.rng.randint(
                            max(MIN_ITEMS_PER_ORDER, items_per_order - ITEMS_VARIANCE),
                            items_per_order + ITEMS_VARIANCE,
                        ),
                        len(product_uuids),
                    )
                    selected_products = factory.rng.sample(product_uuids, num_items)
                    quantities = [
                        factory.rng.randint(MIN_QUANTITY_PER_ITEM, MAX_QUANTITY_PER_ITEM)
                        for _ in range(num_items)
                    ]
                    items_per_order_list.append((selected_products, quantities))

            if not orders_data:
                return 0, 0

            with self.db_manager.get_connection() as conn:
                with conn.cursor() as cur:
                    # Multi-row VALUES insert with RETURNING: one round-trip per
                    # ~16k orders instead of one per order. The DB assigns
                    # order_id, so RETURNING feeds the order_items insert.
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

        total_orders_created = 0
        total_items_created = 0
        total_users_processed = 0

        self.logger.info(f"Processing users in keyset-paginated batches of {user_batch_size}...")
        cursor_key: tuple[datetime, uuid.UUID] | None = None

        with self.db_manager.get_connection() as con:
            with con.cursor() as cur:
                while True:
                    # Keyset pagination on (created_at, user_id): stable page
                    # boundaries (created_at alone is not unique) and no O(n²)
                    # OFFSET rescans on million-row tables.
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
                        self.logger.info("Order -> User processing completed.")
                        break

                    last_user_id, last_created_at = user_batch[-1]
                    cursor_key = (last_created_at, last_user_id)

                    chunk_size = max(1, len(user_batch) // self.thread_count)
                    user_chunks = [
                        user_batch[i:i + chunk_size] for i in range(0, len(user_batch), chunk_size)
                    ]

                    results = list(self.thread_pool_executor.map(process_user_batch_optimized, user_chunks))

                    for orders_created, items_created in results:
                        total_orders_created += orders_created
                        total_items_created += items_created

                    total_users_processed += len(user_batch)
                    self.logger.info(
                        f"-> Processed {total_users_processed} users, "
                        f"{total_orders_created} orders, {total_items_created} items..."
                    )

        self.logger.info(f"Finished generating orders ('single' mode). Processed {total_users_processed} users.")
        self.logger.info(f"Total orders created: {total_orders_created}, Total items created: {total_items_created}")

    def generate_products(self, count: int) -> None:
        self.logger.info(f"Generating {count} products ('single' mode)...")
        factory = get_factory()
        rows = [
            (p.name, p.description, p.price, p.category, p.technical_specs)
            for p in (factory.generate_product() for _ in range(count))
        ]
        self.db_manager.execute_batch(
            "INSERT INTO products (name, description, price, category, technical_specs) "
            "VALUES (%s, %s, %s, %s, %s)",
            rows,
        )
        self.logger.info(f"Finished generating products ('single' mode). Total generated: {len(rows)}")

    def _fetch_product_uuids(self, product_fetch_limit: int) -> list[uuid.UUID]:
        product_rows = self.db_manager.execute_query_fetch_all(
            "SELECT product_id FROM products ORDER BY random() LIMIT %s",
            (product_fetch_limit,),
        )
        product_uuids = [row[0] for row in product_rows]
        if not product_uuids:
            raise RuntimeError("No products found in the database. Cannot generate order items.")
        self.logger.info(f"Fetched {len(product_uuids)} product UUIDs to use for items.")
        return product_uuids
