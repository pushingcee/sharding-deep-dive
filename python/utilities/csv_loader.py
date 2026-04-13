#!/usr/bin/env python3
import logging
import sys
import uuid
from pathlib import Path

from psycopg import Connection, connect

from utilities.config import DbConfig
from utilities.constants import EXIT_FAILURE
from utilities.shard_utils import get_shard_index


class CsvLoader:
    """
    Loads pre-generated CSV data into PostgreSQL via COPY.

    Index files are loaded into memory once (load_indexes()), then each
    user/order/order_item range is seeked directly — no full-file scanning.

    Shard routing is computed at load time from user_id via get_shard_index().
    """

    USERS_CSV = "users.csv"
    PRODUCTS_CSV = "products.csv"
    ORDERS_CSV = "orders.csv"
    ORDER_ITEMS_CSV = "order_items.csv"
    USERS_INDEX = "users.index"
    ORDERS_INDEX = "orders.index"
    ORDER_ITEMS_INDEX = "order_items.index"

    def __init__(self, data_dir: Path, logger_name: str = "dbsetup.csv_loader") -> None:
        self.data_dir = data_dir
        self.logger = logging.getLogger(logger_name)
        # user_id_str → byte offset of that row in users.csv
        self._users_index: dict[str, int] = {}
        # user_id_str → (start_offset, end_offset) in orders.csv
        self._orders_index: dict[str, tuple[int, int]] = {}
        # user_id_str → (start_offset, end_offset) in order_items.csv
        self._order_items_index: dict[str, tuple[int, int]] = {}

    # ------------------------------------------------------------------
    # Index loading
    # ------------------------------------------------------------------

    def load_indexes(self) -> None:
        self.logger.info("Loading index files into memory...")
        self._users_index = self._read_offset_index(self.USERS_INDEX)
        self._orders_index = self._read_range_index(self.ORDERS_INDEX)
        self._order_items_index = self._read_range_index(self.ORDER_ITEMS_INDEX)
        self.logger.info(
            f"Indexes loaded: {len(self._users_index):,} users, "
            f"{len(self._orders_index):,} order ranges, "
            f"{len(self._order_items_index):,} order_item ranges"
        )

    def _read_offset_index(self, filename: str) -> dict[str, int]:
        index: dict[str, int] = {}
        with open(self.data_dir / filename) as f:
            next(f)  # skip header
            for line in f:
                uid, offset = line.rstrip("\n").split(",")
                index[uid] = int(offset)
        return index

    def _read_range_index(self, filename: str) -> dict[str, tuple[int, int]]:
        index: dict[str, tuple[int, int]] = {}
        with open(self.data_dir / filename) as f:
            next(f)  # skip header
            for line in f:
                uid, start, end = line.rstrip("\n").split(",")
                index[uid] = (int(start), int(end))
        return index

    def _first_n_user_ids(self, n: int) -> list[str]:
        """Return the first N user IDs in insertion order (dict preserves insertion order in Python 3.7+)."""
        return list(self._users_index.keys())[:n]

    # ------------------------------------------------------------------
    # Public load methods
    # ------------------------------------------------------------------

    def load_single(self, db_config: DbConfig, users_count: int) -> None:
        self.logger.info(f"Loading {users_count:,} users from CSV (single mode)...")
        user_ids = self._first_n_user_ids(users_count)
        try:
            with connect(str(db_config), autocommit=False) as conn:
                self._copy_products(conn)
                self._copy_users(conn, user_ids)
                self._copy_orders(conn, user_ids)
                self._copy_order_items(conn, user_ids)
                conn.commit()
        except Exception as e:
            self.logger.error(f"Error loading CSV data (single mode): {e}")
            sys.exit(EXIT_FAILURE)
        self.logger.info("Single mode CSV load complete.")

    def load_sharded(self, shard_configs: tuple[DbConfig, ...], users_count: int) -> None:
        self.logger.info(f"Loading {users_count:,} users from CSV (sharded mode)...")
        user_ids = self._first_n_user_ids(users_count)
        users_by_shard = self._group_by_shard(user_ids)

        try:
            for shard_idx, shard_user_ids in users_by_shard.items():
                with connect(str(shard_configs[shard_idx]), autocommit=False) as conn:
                    self._copy_products(conn)
                    self._copy_users(conn, shard_user_ids)
                    self._copy_orders(conn, shard_user_ids)
                    self._copy_order_items(conn, shard_user_ids)
                    conn.commit()
                self.logger.info(f"Shard {shard_idx + 1}: loaded {len(shard_user_ids):,} users.")
        except Exception as e:
            self.logger.error(f"Error loading CSV data (sharded mode): {e}")
            sys.exit(EXIT_FAILURE)
        self.logger.info("Sharded mode CSV load complete.")

    def load_sharded_lookup(
        self,
        shard_configs: tuple[DbConfig, ...],
        main_db_config: DbConfig,
        users_count: int,
    ) -> None:
        self.logger.info(f"Loading {users_count:,} users from CSV (sharded-lookup-table mode)...")
        user_ids = self._first_n_user_ids(users_count)
        users_by_shard = self._group_by_shard(user_ids)

        try:
            for shard_idx, shard_user_ids in users_by_shard.items():
                with connect(str(shard_configs[shard_idx]), autocommit=False) as conn:
                    self._copy_products(conn)
                    self._copy_users(conn, shard_user_ids)
                    self._copy_orders(conn, shard_user_ids)
                    self._copy_order_items(conn, shard_user_ids)
                    conn.commit()
                self.logger.info(f"Shard {shard_idx + 1}: loaded {len(shard_user_ids):,} users.")

            with connect(str(main_db_config), autocommit=False) as main_conn:
                self._copy_lookup_entries(main_conn, users_by_shard)
                main_conn.commit()
        except Exception as e:
            self.logger.error(f"Error loading CSV data (sharded-lookup-table mode): {e}")
            sys.exit(EXIT_FAILURE)
        self.logger.info("Sharded lookup-table mode CSV load complete.")

    # ------------------------------------------------------------------
    # COPY helpers
    # ------------------------------------------------------------------

    def _copy_products(self, conn: Connection) -> None:
        """Stream entire products.csv — products are always fully loaded (reference table)."""
        path = self.data_dir / self.PRODUCTS_CSV
        with conn.cursor() as cur:
            with cur.copy(
                "COPY products (product_id, name, description, price, category, technical_specs) "
                "FROM STDIN (FORMAT CSV, HEADER true, NULL '')"
            ) as copy:
                with open(path, "rb") as f:
                    while chunk := f.read(65536):
                        copy.write(chunk)
        self.logger.debug("Products copied.")

    def _copy_users(self, conn: Connection, user_ids: list[str]) -> None:
        """Seek to each user's offset and write that single row."""
        path = self.data_dir / self.USERS_CSV
        with conn.cursor() as cur:
            with cur.copy(
                "COPY users (user_id, email, first_name, last_name, country, created_at, last_active, preferences) "
                "FROM STDIN (FORMAT CSV, NULL '')"
            ) as copy:
                with open(path, "rb") as f:
                    for uid in user_ids:
                        f.seek(self._users_index[uid])
                        copy.write(f.readline())
        self.logger.debug(f"Copied {len(user_ids):,} users.")

    def _copy_orders(self, conn: Connection, user_ids: list[str]) -> None:
        """Seek to each user's contiguous order block and stream it in one read."""
        path = self.data_dir / self.ORDERS_CSV
        with conn.cursor() as cur:
            with cur.copy(
                "COPY orders (order_id, user_id, order_date, total_amount, status) "
                "FROM STDIN (FORMAT CSV, NULL '')"
            ) as copy:
                with open(path, "rb") as f:
                    for uid in user_ids:
                        start, end = self._orders_index[uid]
                        if end > start:
                            f.seek(start)
                            copy.write(f.read(end - start))
        self.logger.debug(f"Copied orders for {len(user_ids):,} users.")

    def _copy_order_items(self, conn: Connection, user_ids: list[str]) -> None:
        """Seek to each user's contiguous order_items block and stream it in one read."""
        path = self.data_dir / self.ORDER_ITEMS_CSV
        with conn.cursor() as cur:
            with cur.copy(
                "COPY order_items (order_id, product_id, quantity) "
                "FROM STDIN (FORMAT CSV, NULL '')"
            ) as copy:
                with open(path, "rb") as f:
                    for uid in user_ids:
                        start, end = self._order_items_index[uid]
                        if end > start:
                            f.seek(start)
                            copy.write(f.read(end - start))
        self.logger.debug(f"Copied order_items for {len(user_ids):,} users.")

    def _copy_lookup_entries(self, conn: Connection, users_by_shard: dict[int, list[str]]) -> None:
        rows: list[tuple[str, int]] = [
            (uid, shard_idx + 1)
            for shard_idx, uids in users_by_shard.items()
            for uid in uids
        ]
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO user_data_shard (user_id, shard_id) VALUES (%s, %s)",
                rows,
            )
        self.logger.debug(f"Inserted {len(rows):,} lookup table entries.")

    # ------------------------------------------------------------------
    # Routing
    # ------------------------------------------------------------------

    def _group_by_shard(self, user_ids: list[str]) -> dict[int, list[str]]:
        users_by_shard: dict[int, list[str]] = {}
        for uid in user_ids:
            shard_idx = get_shard_index(uuid.UUID(uid))
            users_by_shard.setdefault(shard_idx, []).append(uid)
        return users_by_shard
