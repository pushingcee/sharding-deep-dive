#!/usr/bin/env python3
import csv
import io
import logging
import uuid
from pathlib import Path
from typing import Any

from utilities.constants import (
    CSV_LOG_INTERVAL,
    DEFAULT_ITEMS_PER_ORDER,
    DEFAULT_ORDERS_PER_USER,
    DEFAULT_PRODUCTS_COUNT,
    ITEMS_VARIANCE,
    MIN_ITEMS_PER_ORDER,
    MIN_QUANTITY_PER_ITEM,
    MAX_QUANTITY_PER_ITEM,
    ORDERS_VARIANCE,
    PRODUCT_LOG_INTERVAL,
)
from utilities.data_factory import DataFactory

_USERS_HEADER = ["user_id", "email", "first_name", "last_name", "country", "created_at", "last_active", "preferences"]
_PRODUCTS_HEADER = ["product_id", "name", "description", "price", "category", "technical_specs"]
_ORDERS_HEADER = ["order_id", "user_id", "order_date", "total_amount", "status"]
_ORDER_ITEMS_HEADER = ["order_id", "product_id", "quantity"]

_USERS_INDEX_HEADER = ["user_id", "byte_offset"]
_ORDERS_INDEX_HEADER = ["user_id", "start_offset", "end_offset"]
_ORDER_ITEMS_INDEX_HEADER = ["user_id", "start_offset", "end_offset"]


def _row_to_bytes(row: list[Any]) -> bytes:
    """Serialize a CSV row to bytes, converting None to empty string for PostgreSQL NULL."""
    buf = io.StringIO()
    csv.writer(buf).writerow(["" if v is None else v for v in row])
    return buf.getvalue().encode("utf-8")


class CsvGenerator:
    """
    Generates normalized CSV files + binary-offset index files for the entire dataset.

    Output (all in data_dir):
        users.csv          — one row per user
        products.csv       — one row per product
        orders.csv         — all orders, grouped by user (sequential per user)
        order_items.csv    — all order items, grouped by user (sequential per user)
        users.index        — user_id → byte offset in users.csv
        orders.index       — user_id → (start, end) byte range in orders.csv
        order_items.index  — user_id → (start, end) byte range in order_items.csv

    Shard routing is NOT stored — it is recomputed at load time from user_id.
    """

    USERS_CSV = "users.csv"
    PRODUCTS_CSV = "products.csv"
    ORDERS_CSV = "orders.csv"
    ORDER_ITEMS_CSV = "order_items.csv"
    USERS_INDEX = "users.index"
    ORDERS_INDEX = "orders.index"
    ORDER_ITEMS_INDEX = "order_items.index"

    _REQUIRED_FILES = (
        USERS_CSV, PRODUCTS_CSV, ORDERS_CSV, ORDER_ITEMS_CSV,
        USERS_INDEX, ORDERS_INDEX, ORDER_ITEMS_INDEX,
    )

    def __init__(self, data_dir: Path, logger_name: str = "dbsetup.csv_generator", seed: int | None = None) -> None:
        self.data_dir = data_dir
        self.logger = logging.getLogger(logger_name)
        # CSV generation is single-threaded, so one seeded factory makes the
        # whole dataset reproducible: same seed → same CSVs.
        self._factory = DataFactory(seed=seed)

    def data_exists(self) -> bool:
        return all((self.data_dir / f).exists() for f in self._REQUIRED_FILES)

    def generate_all(
        self,
        users_count: int,
        products_count: int = DEFAULT_PRODUCTS_COUNT,
        orders_per_user: int = DEFAULT_ORDERS_PER_USER,
        items_per_order: int = DEFAULT_ITEMS_PER_ORDER,
    ) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.logger.info(
            f"Generating CSV dataset to '{self.data_dir}' — "
            f"{users_count:,} users / {products_count:,} products / "
            f"~{orders_per_user} orders/user / ~{items_per_order} items/order"
        )
        product_uuids = self._generate_products(products_count)
        self._generate_users_orders_items(users_count, orders_per_user, items_per_order, product_uuids)
        self.logger.info("CSV generation complete.")

    # ------------------------------------------------------------------
    # Internal generation methods
    # ------------------------------------------------------------------

    def _generate_products(self, count: int) -> list[uuid.UUID]:
        self.logger.info(f"Generating {count:,} products...")
        product_uuids: list[uuid.UUID] = []
        path = self.data_dir / self.PRODUCTS_CSV

        with open(path, "wb") as f:
            f.write(_row_to_bytes(_PRODUCTS_HEADER))
            for i in range(count):
                product = self._factory.generate_product()
                product_uuids.append(product.product_uuid)
                f.write(_row_to_bytes([
                    product.product_uuid,
                    product.name,
                    product.description,
                    product.price,
                    product.category,
                    product.technical_specs,
                ]))
                if (i + 1) % PRODUCT_LOG_INTERVAL == 0:
                    self.logger.info(f"-> {i + 1:,}/{count:,} products")

        self.logger.info(f"Products written to {path}")
        return product_uuids

    def _generate_users_orders_items(
        self,
        users_count: int,
        orders_per_user: int,
        items_per_order: int,
        product_uuids: list[uuid.UUID],
    ) -> None:
        self.logger.info(f"Generating {users_count:,} users with orders and order items...")

        with (
            open(self.data_dir / self.USERS_CSV, "wb") as u_f,
            open(self.data_dir / self.ORDERS_CSV, "wb") as o_f,
            open(self.data_dir / self.ORDER_ITEMS_CSV, "wb") as oi_f,
            open(self.data_dir / self.USERS_INDEX, "w") as u_idx,
            open(self.data_dir / self.ORDERS_INDEX, "w") as o_idx,
            open(self.data_dir / self.ORDER_ITEMS_INDEX, "w") as oi_idx,
        ):
            u_f.write(_row_to_bytes(_USERS_HEADER))
            o_f.write(_row_to_bytes(_ORDERS_HEADER))
            oi_f.write(_row_to_bytes(_ORDER_ITEMS_HEADER))
            u_idx.write(",".join(_USERS_INDEX_HEADER) + "\n")
            o_idx.write(",".join(_ORDERS_INDEX_HEADER) + "\n")
            oi_idx.write(",".join(_ORDER_ITEMS_INDEX_HEADER) + "\n")

            for i in range(users_count):
                user = self._factory.generate_user(sharded=False)

                # ---- user row ----
                u_offset = u_f.tell()
                u_f.write(_row_to_bytes([
                    user.user_uuid, user.email, user.first_name, user.last_name,
                    user.country, user.created_at, user.last_active, user.preferences,
                ]))
                u_idx.write(f"{user.user_uuid},{u_offset}\n")

                # ---- orders + order_items for this user ----
                o_start = o_f.tell()
                oi_start = oi_f.tell()

                num_orders = self._factory.rng.randint(
                    max(0, orders_per_user - ORDERS_VARIANCE),
                    orders_per_user + ORDERS_VARIANCE,
                )
                for _ in range(num_orders):
                    order = self._factory.generate_orders_for_user(user.user_uuid, user.created_at)
                    order_uuid = uuid.uuid4()
                    o_f.write(_row_to_bytes([
                        order_uuid, user.user_uuid, order.order_date,
                        order.total_amount, order.status,
                    ]))

                    num_items = min(
                        self._factory.rng.randint(
                            max(MIN_ITEMS_PER_ORDER, items_per_order - ITEMS_VARIANCE),
                            items_per_order + ITEMS_VARIANCE,
                        ),
                        len(product_uuids),
                    )
                    for product_uuid in self._factory.rng.sample(product_uuids, num_items):
                        quantity = self._factory.rng.randint(MIN_QUANTITY_PER_ITEM, MAX_QUANTITY_PER_ITEM)
                        oi_f.write(_row_to_bytes([order_uuid, product_uuid, quantity]))

                o_idx.write(f"{user.user_uuid},{o_start},{o_f.tell()}\n")
                oi_idx.write(f"{user.user_uuid},{oi_start},{oi_f.tell()}\n")

                if (i + 1) % CSV_LOG_INTERVAL == 0:
                    pct = (i + 1) / users_count * 100
                    self.logger.info(f"-> {i + 1:,}/{users_count:,} users ({pct:.0f}%)")

        self.logger.info("Users, orders, and order items written.")
