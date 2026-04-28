package org.learn.repository.commons;

import org.learn.domain.User;
import org.learn.domain.product.Product;
import org.springframework.jdbc.core.RowMapper;

import java.util.UUID;

public class RowMappers {
    public static  RowMapper<User> USER_ROW_MAPPER =
         (rs, rowNum) -> {
            User user = new User();
            user.setUser_id(UUID.fromString(rs.getString("user_id")));
            user.setFirstName(rs.getString("first_name"));
            user.setLastName(rs.getString("last_name"));
            user.setEmail(rs.getString("email"));
            user.setCountry(rs.getString("country"));
            user.setCreatedAt(rs.getTimestamp("created_at").toLocalDateTime());
            if (rs.getDate("last_active") != null) {
                user.setLastActive(rs.getDate("last_active").toLocalDate());
            }
            return user;
        };

    public static RowMapper<Product> PRODUCT_ROW_MAPPER = (rs, rowNum) -> {
            Product product = new Product();
            product.setProduct_id(UUID.fromString(rs.getString("product_id")));
            product.setName(rs.getString("name"));
            product.setDescription(rs.getString("description"));
            product.setPrice(rs.getBigDecimal("price"));
            product.setCategory(rs.getString("category"));
            return product;
    };

}
