package org.learn.repository.commons;

/**
 * Shared SQL for order reads.
 *
 * Every strategy (single, sharded, lookup) must issue byte-identical
 * statements so the benchmark measures the routing architecture above the
 * database, not accidental differences in query shape. Do not fork these
 * strings per profile — the per-strategy difference belongs in *where* the
 * statement is sent (which shard, how many shards), never in the SQL itself.
 */
public final class OrderSql {

    public static final String ORDER_COLS =
        "o.order_id, o.user_id, o.total_amount, o.status, o.order_date, " +
        "u.first_name, u.last_name, u.email, u.country, " +
        "u.created_at AS u_created_at, u.last_active AS u_last_active";

    public static final String FROM_ORDERS_JOIN_USERS =
        " FROM orders o JOIN users u ON o.user_id = u.user_id";

    public static final String FIND_BY_ID =
        "SELECT " + ORDER_COLS + FROM_ORDERS_JOIN_USERS + " WHERE o.order_id = ?";

    public static final String FIND_BY_USER_ID =
        "SELECT " + ORDER_COLS + FROM_ORDERS_JOIN_USERS + " WHERE o.user_id = ?";

    public static final String FIND_ALL =
        "SELECT " + ORDER_COLS + FROM_ORDERS_JOIN_USERS;

    public static final String PAGE_KEYSET_FIRST =
        "SELECT " + ORDER_COLS + FROM_ORDERS_JOIN_USERS +
        " ORDER BY o.order_date DESC, o.order_id DESC LIMIT ?";

    public static final String PAGE_KEYSET_NEXT =
        "SELECT " + ORDER_COLS + FROM_ORDERS_JOIN_USERS +
        " WHERE o.order_date < ? OR (o.order_date = ? AND o.order_id < ?)" +
        " ORDER BY o.order_date DESC, o.order_id DESC LIMIT ?";

    public static final String INSERT =
        "INSERT INTO orders (order_id, user_id, total_amount, status) VALUES (?, ?, ?, ?)";

    public static final String UPDATE =
        "UPDATE orders SET user_id = ?, total_amount = ?, status = ? WHERE order_id = ?";

    private OrderSql() {
    }
}
