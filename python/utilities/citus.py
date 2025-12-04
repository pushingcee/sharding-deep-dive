from .commons.queries import create_tables as create_tables_base

def create_tables(cur) -> None:
    create_tables_base(cur)
    citus_shard_tables(cur)

def citus_shard_tables(cur):
    cur.execute("""
            ALTER TABLE order_items DROP CONSTRAINT order_items_order_id_fkey;
        """)
    cur.execute("""
            SELECT create_reference_table('users');
        """)
    cur.execute("""
            SELECT create_reference_table('products');
        """)
    cur.execute("""
            SELECT create_distributed_table('orders','order_id')
        """)
    cur.execute("""
            SELECT create_distributed_table('order_items','order_id', colocate_with => 'orders')
        """)

