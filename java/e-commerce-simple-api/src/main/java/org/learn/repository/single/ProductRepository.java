package org.learn.repository.single;

import org.learn.domain.product.Product;
import org.learn.repository.commons.ProductSql;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Profile;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

import javax.sql.DataSource;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

import static org.learn.repository.commons.RowMappers.PRODUCT_ROW_MAPPER;

/**
 * Single-DB product access. Same SQL and JdbcTemplate stack as the sharded
 * and lookup repositories (which read products from shard 0, since products
 * are replicated everywhere).
 */
@Profile("single")
@Repository
public class ProductRepository implements org.learn.repository.ProductRepository {

    private final JdbcTemplate jdbcTemplate;

    @Autowired
    public ProductRepository(DataSource dataSource) {
        this.jdbcTemplate = new JdbcTemplate(dataSource);
    }

    public Optional<Product> findById(UUID productId) {
        List<Product> products = jdbcTemplate.query(ProductSql.FIND_BY_ID, PRODUCT_ROW_MAPPER, productId);
        return products.isEmpty() ? Optional.empty() : Optional.of(products.get(0));
    }
}
