def create_lookup_table(cur):
    cur.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto;")
    cur.execute(USERS_CREATE_LOOKUP_TABLE_QUERY)

def create_tables(cur):
    cur.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto;")
    cur.execute(USERS_TABLE_QUERY)
    cur.execute(PRODUCTS_TABLE_QUERY)
    cur.execute(ORDERS_TABLE_QUERY)
    cur.execute(ORDER_ITEMS_TABLE_QUERY)

USERS_TABLE_QUERY: str = """
        CREATE TABLE IF NOT EXISTS users (
            user_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            first_name VARCHAR(50) NOT NULL,
            last_name VARCHAR(50) NOT NULL,
            email VARCHAR(100) UNIQUE NOT NULL,
            country CHAR(2) NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            last_active DATE,
            preferences JSONB
        )"""

PRODUCTS_TABLE_QUERY: str = """
        CREATE TABLE IF NOT EXISTS products (
            product_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name VARCHAR(255) NOT NULL,
            description TEXT,
            price NUMERIC(10,2) NOT NULL,
            category VARCHAR(50),
            technical_specs JSONB,
            search_vector TSVECTOR GENERATED ALWAYS AS (
                to_tsvector('english',
                    coalesce(name, '') || ' ' ||
                    coalesce(description, '') || ' ' ||
                    coalesce(technical_specs::text, '')
                )
            ) STORED
        );
    """

ORDERS_TABLE_QUERY: str = """
        CREATE TABLE IF NOT EXISTS orders(
            order_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID REFERENCES users(user_id),
            order_date TIMESTAMP WITH TIME ZONE NOT NULL, 
            total_amount DECIMAL(10,2) NOT NULL,
            status VARCHAR(20) CHECK (status IN ('pending','shipped','delivered','cancelled'))
        )
    """

USERS_CREATE_LOOKUP_TABLE_QUERY: str = """
        CREATE TABLE IF NOT EXISTS user_data_shard(
            user_id UUID PRIMARY KEY NOT NULL,
            shard_id INTEGER NOT NULL
        )
    """

ORDER_ITEMS_TABLE_QUERY: str = """
        CREATE TABLE IF NOT EXISTS order_items (
            order_id UUID REFERENCES orders(order_id) ON DELETE CASCADE,
            product_id UUID REFERENCES products(product_id) ON DELETE RESTRICT, 
            quantity INTEGER NOT NULL CHECK (quantity > 0), 
            PRIMARY KEY (order_id, product_id)
        )
    """