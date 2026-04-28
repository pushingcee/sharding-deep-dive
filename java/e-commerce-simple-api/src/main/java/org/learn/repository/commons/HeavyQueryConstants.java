package org.learn.repository.commons;

import org.learn.domain.AnalyticsResult;
import org.learn.domain.analytics.CountryPartialRow;
import org.learn.domain.analytics.CountryProductPair;
import org.learn.domain.analytics.ProductPartialRow;
import org.learn.domain.analytics.UserStatsRow;
import org.springframework.jdbc.core.RowMapper;

import java.math.BigDecimal;
import java.util.UUID;

public class HeavyQueryConstants {

    /**
     * Single-DB analytics rollup. Caller must supply 6 params in this exact
     * order: from, to, from, to, from, to — one pair per CTE. Varying the
     * window per call defeats HTTP/result caches and changes which heap
     * slices are touched (whether that actually evicts shared_buffers depends
     * on table size vs cache — verify with EXPLAIN (ANALYZE, BUFFERS)).
     *
     * Notes on quirks intentionally preserved (so sharded fan-out can
     * reproduce identical numbers):
     *   - product_performance uses LEFT JOIN ... WHERE pattern that
     *     effectively becomes INNER (excludes 0-activity products from
     *     COUNT(*)). The fan-out matches by using INNER JOIN throughout.
     *   - country_analytics.total_revenue is inflated by avg-items-per-order
     *     because SUM(o.total_amount) runs after JOIN order_items duplicates
     *     the row.
     * Both are real SQL bugs worth fixing later, but matching them means
     * single and sharded report the same numbers today.
     */
    public static final String HEAVY_ANALYTICS_QUERY = """
            WITH user_order_stats AS (
                SELECT
                    u.user_id,
                    u.first_name,
                    u.last_name,
                    u.country,
                    COUNT(o.order_id) as total_orders,
                    SUM(o.total_amount) as total_spent,
                    AVG(o.total_amount) as avg_order_value,
                    MAX(o.order_date) as last_order_date,
                    COUNT(CASE WHEN o.status = 'delivered' THEN 1 END) as delivered_orders,
                    COUNT(CASE WHEN o.status = 'cancelled' THEN 1 END) as cancelled_orders
                FROM users u
                JOIN orders o ON u.user_id = o.user_id
                WHERE o.order_date BETWEEN ? AND ?
                GROUP BY u.user_id, u.first_name, u.last_name, u.country
            ),
            product_performance AS (
                SELECT
                    p.product_id,
                    p.name,
                    p.category,
                    p.price,
                    COUNT(oi.order_id) as times_ordered,
                    SUM(oi.quantity) as total_quantity_sold,
                    SUM(oi.quantity * p.price) as total_revenue,
                    COUNT(DISTINCT o.user_id) as unique_customers
                FROM products p
                LEFT JOIN order_items oi ON p.product_id = oi.product_id
                LEFT JOIN orders o ON oi.order_id = o.order_id
                WHERE o.order_date BETWEEN ? AND ?
                GROUP BY p.product_id, p.name, p.category, p.price
            ),
            country_analytics AS (
                SELECT
                    u.country,
                    COUNT(DISTINCT u.user_id) as total_users,
                    COUNT(DISTINCT o.order_id) as total_orders,
                    SUM(o.total_amount) as total_revenue,
                    AVG(o.total_amount) as avg_order_value,
                    COUNT(DISTINCT p.product_id) as unique_products_ordered
                FROM users u
                JOIN orders o ON u.user_id = o.user_id
                LEFT JOIN order_items oi ON o.order_id = oi.order_id
                LEFT JOIN products p ON oi.product_id = p.product_id
                WHERE o.order_date BETWEEN ? AND ?
                GROUP BY u.country
            )
            SELECT
                'User Analytics' as report_type,
                COUNT(*) as total_count,
                SUM(total_orders) as total_orders,
                SUM(total_spent) as total_revenue,
                AVG(avg_order_value) as average_value,
                COUNT(CASE WHEN total_orders > 10 THEN 1 END) as special_count
            FROM user_order_stats
            UNION ALL
            SELECT
                'Product Analytics' as report_type,
                COUNT(*) as total_count,
                SUM(times_ordered) as total_orders,
                SUM(total_revenue) as total_revenue,
                AVG(total_quantity_sold) as average_value,
                COUNT(CASE WHEN total_revenue > 10000 THEN 1 END) as special_count
            FROM product_performance
            UNION ALL
            SELECT
                'Country Analytics' as report_type,
                COUNT(*) as total_count,
                SUM(total_orders) as total_orders,
                SUM(total_revenue) as total_revenue,
                AVG(avg_order_value) as average_value,
                COUNT(CASE WHEN total_revenue > 50000 THEN 1 END) as special_count
            FROM country_analytics
            """;

    public static final RowMapper<AnalyticsResult> ANALYTICS_RESULT_ROW_MAPPER = (rs, rowNum) -> new AnalyticsResult(
            rs.getString("report_type"),
            rs.getLong("total_count"),
            rs.getLong("total_orders"),
            rs.getBigDecimal("total_revenue"),
            rs.getBigDecimal("average_value"),
            rs.getLong("special_count"));

    // ===== Sharded fan-out: per-shard partial queries =====
    //
    // The single-DB query above does CTE rollups in one shot. Across shards
    // those rollups can't be summed naively — DISTINCT aggregates and
    // per-group thresholds break (countries appear on multiple shards,
    // products are replicated, etc). The shard-side queries below produce
    // *unaggregated* row groups; the coordinator (AnalyticsFanOut) does the
    // GROUP BY across shards in app code. Cost of correctness: more network,
    // more memory, more code.

    /** Per-user stats on this shard. Users are partitioned, so each row is
     *  globally complete — coordinator just unions. */
    public static final String USER_STATS_PARTIAL_SQL = """
            SELECT
                COUNT(o.order_id) as total_orders,
                SUM(o.total_amount) as total_spent,
                AVG(o.total_amount) as avg_order_value
            FROM users u
            JOIN orders o ON u.user_id = o.user_id
            WHERE o.order_date BETWEEN ? AND ?
            GROUP BY u.user_id
            """;

    public static final RowMapper<UserStatsRow> USER_STATS_ROW_MAPPER = (rs, rowNum) -> new UserStatsRow(
            rs.getLong("total_orders"),
            nullSafeBig(rs.getBigDecimal("total_spent")),
            nullSafeBig(rs.getBigDecimal("avg_order_value")));

    /** Per-product slice on this shard. Only products with activity in the
     *  window are returned; total catalog size comes from PRODUCT_COUNT_SQL.
     *  unique_customers is summable across shards (users disjoint). */
    public static final String PRODUCT_PARTIAL_SQL = """
            SELECT
                p.product_id,
                COUNT(oi.order_id) as times_ordered,
                COALESCE(SUM(oi.quantity), 0) as total_quantity_sold,
                COALESCE(SUM(oi.quantity * p.price), 0) as total_revenue,
                COUNT(DISTINCT o.user_id) as unique_customers
            FROM products p
            JOIN order_items oi ON p.product_id = oi.product_id
            JOIN orders o ON oi.order_id = o.order_id
            WHERE o.order_date BETWEEN ? AND ?
            GROUP BY p.product_id
            """;

    public static final RowMapper<ProductPartialRow> PRODUCT_PARTIAL_ROW_MAPPER = (rs, rowNum) -> new ProductPartialRow(
            UUID.fromString(rs.getString("product_id")),
            rs.getLong("times_ordered"),
            rs.getLong("total_quantity_sold"),
            nullSafeBig(rs.getBigDecimal("total_revenue")),
            rs.getLong("unique_customers"));

    /** Per-country slice on this shard. joined_row_count is needed at the
     *  coordinator to recompute AVG(total_amount) weighted across shards
     *  (matches the single-DB CTE which inflates by items-per-order). */
    public static final String COUNTRY_PARTIAL_SQL = """
            SELECT
                u.country,
                COUNT(DISTINCT u.user_id) as total_users,
                COUNT(DISTINCT o.order_id) as total_orders,
                COALESCE(SUM(o.total_amount), 0) as total_revenue,
                COUNT(o.order_id) as joined_row_count
            FROM users u
            JOIN orders o ON u.user_id = o.user_id
            LEFT JOIN order_items oi ON o.order_id = oi.order_id
            LEFT JOIN products p ON oi.product_id = p.product_id
            WHERE o.order_date BETWEEN ? AND ?
            GROUP BY u.country
            """;

    public static final RowMapper<CountryPartialRow> COUNTRY_PARTIAL_ROW_MAPPER = (rs, rowNum) -> new CountryPartialRow(
            rs.getString("country"),
            rs.getLong("total_users"),
            rs.getLong("total_orders"),
            nullSafeBig(rs.getBigDecimal("total_revenue")),
            rs.getLong("joined_row_count"));

    /** Distinct (country, product_id) pairs for this shard. Coordinator
     *  unions and dedupes to compute unique_products_ordered per country. */
    public static final String COUNTRY_PRODUCT_PAIRS_SQL = """
            SELECT DISTINCT u.country, oi.product_id
            FROM users u
            JOIN orders o ON u.user_id = o.user_id
            JOIN order_items oi ON o.order_id = oi.order_id
            WHERE o.order_date BETWEEN ? AND ?
            """;

    public static final RowMapper<CountryProductPair> COUNTRY_PRODUCT_PAIR_ROW_MAPPER = (rs, rowNum) -> new CountryProductPair(
            rs.getString("country"),
            UUID.fromString(rs.getString("product_id")));

    /** Total catalog size. Products are replicated across shards, so any
     *  shard answers correctly. Used for Product Analytics total_count. */
    public static final String PRODUCT_COUNT_SQL = "SELECT COUNT(*) FROM products";

    private static BigDecimal nullSafeBig(BigDecimal v) {
        return v == null ? BigDecimal.ZERO : v;
    }

    private HeavyQueryConstants() {
        // Utility class - prevent instantiation
    }
}
