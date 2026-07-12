package org.learn.repository.sharded;

import org.learn.domain.product.Product;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Profile;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

import java.util.List;
import java.util.Optional;
import java.util.UUID;

import static org.learn.repository.commons.RowMappers.PRODUCT_ROW_MAPPER;

/**
 * Products are a reference table replicated to every shard, so all reads go
 * to shard 0 — any shard would answer identically.
 */
@Profile("sharded")
@Repository
public class ProductRepository implements org.learn.repository.ProductRepository {

    private final JdbcTemplate jdbcTemplate;

    @Autowired
    public ProductRepository(ShardedDataSource shardedDataSource) {
        this.jdbcTemplate = new JdbcTemplate(shardedDataSource.getDataSourceByIndex(0));
    }

    public Optional<Product> findById(UUID productId) {
        String sql = "SELECT product_id, name, description, price, category FROM products WHERE product_id = ?";
        List<Product> products = jdbcTemplate.query(sql, PRODUCT_ROW_MAPPER, productId.toString());
        return products.isEmpty() ? Optional.empty() : Optional.of(products.get(0));
    }

    public List<Product> findAll() {
        String sql = "SELECT product_id, name, description, price, category FROM products";
        return jdbcTemplate.query(sql, PRODUCT_ROW_MAPPER);
    }
}
