package org.learn.repository.lookup;

import org.learn.domain.product.Product;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Profile;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.stereotype.Repository;

import javax.sql.DataSource;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

import static org.learn.repository.commons.RowMappers.PRODUCT_ROW_MAPPER;

@Profile("lookup")
@Repository
public class ProductRepository implements org.learn.repository.ProductRepository {
    
    private final ShardedDataSource shardedDataSource;

    @Autowired
    public ProductRepository(ShardedDataSource shardedDataSource) {
        this.shardedDataSource = shardedDataSource;
    }
    
    public Optional<Product> findById(UUID productId) {
        DataSource shardDataSource = shardedDataSource.getDataSourceByIndex(0); // Use first shard
        JdbcTemplate jdbcTemplate = new JdbcTemplate(shardDataSource);
        
        try {
            String sql = "SELECT product_id, name, description, price, category FROM products WHERE product_id = ?";
            List<Product> products = jdbcTemplate.query(sql, PRODUCT_ROW_MAPPER, productId.toString());
            
            if (!products.isEmpty()) {
                return Optional.of(products.get(0));
            }
        } catch (Exception e) {
            System.err.println("Error finding product by ID: " + e.getMessage());
        }
        return Optional.empty();
    }
    
    public List<Product> findAll() {
        DataSource shardDataSource = shardedDataSource.getDataSourceByIndex(0);
        JdbcTemplate jdbcTemplate = new JdbcTemplate(shardDataSource);
        
        try {
            String sql = "SELECT product_id, name, description, price, category FROM products";
            return jdbcTemplate.query(sql, PRODUCT_ROW_MAPPER);
        } catch (Exception e) {
            System.err.println("Error finding all products: " + e.getMessage());
            return new ArrayList<>();
        }
    }
    
    public List<Product> findByCategory(String category) {
        DataSource shardDataSource = shardedDataSource.getDataSourceByIndex(0);
        JdbcTemplate jdbcTemplate = new JdbcTemplate(shardDataSource);
        
        try {
            String sql = "SELECT product_id, name, description, price, category FROM products WHERE category = ?";
            return jdbcTemplate.query(sql, PRODUCT_ROW_MAPPER, category);
        } catch (Exception e) {
            System.err.println("Error finding products by category: " + e.getMessage());
            return new ArrayList<>();
        }
    }
    
    public List<Product> findByPriceRange(java.math.BigDecimal minPrice, java.math.BigDecimal maxPrice) {
        DataSource shardDataSource = shardedDataSource.getDataSourceByIndex(0);
        JdbcTemplate jdbcTemplate = new JdbcTemplate(shardDataSource);
        
        try {
            String sql = "SELECT product_id, name, description, price, category FROM products WHERE price BETWEEN ? AND ?";
            return jdbcTemplate.query(sql, PRODUCT_ROW_MAPPER, minPrice, maxPrice);
        } catch (Exception e) {
            System.err.println("Error finding products by price range: " + e.getMessage());
            return new ArrayList<>();
        }
    }
}
