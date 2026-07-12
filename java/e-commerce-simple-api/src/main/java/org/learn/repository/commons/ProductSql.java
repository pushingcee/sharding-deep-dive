package org.learn.repository.commons;

/**
 * Shared SQL for product reads — same statement in every strategy. Products
 * are replicated to every shard, so sharded/lookup profiles read shard 0.
 */
public final class ProductSql {

    public static final String FIND_BY_ID =
        "SELECT product_id, name, description, price, category, technical_specs " +
        "FROM products WHERE product_id = ?";

    private ProductSql() {
    }
}
