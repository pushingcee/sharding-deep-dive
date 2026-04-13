from typing import Any

from psycopg import Cursor

from utilities.queries import create_tables as create_tables_base


def create_tables(cur: Cursor[Any]) -> None:
    create_tables_base(cur)
    _citus_shard_tables(cur)


def _citus_shard_tables(cur: Cursor[Any]) -> None:
    cur.execute("ALTER TABLE order_items DROP CONSTRAINT order_items_order_id_fkey;")
    cur.execute("SELECT create_reference_table('users');")
    cur.execute("SELECT create_reference_table('products');")
    cur.execute("SELECT create_distributed_table('orders','order_id')")
    cur.execute("SELECT create_distributed_table('order_items','order_id', colocate_with => 'orders')")
