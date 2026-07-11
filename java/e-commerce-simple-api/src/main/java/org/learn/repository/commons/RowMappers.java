package org.learn.repository.commons;

import org.learn.domain.Order;
import org.learn.domain.User;
import org.learn.domain.product.Product;
import org.springframework.jdbc.core.RowMapper;

import java.sql.Date;
import java.time.OffsetDateTime;
import java.util.UUID;

public class RowMappers {

    /**
     * Maps a row produced by {@link OrderSql#ORDER_COLS} (orders joined to
     * users). Shared by all strategies so hydration cost is identical.
     */
    public static final RowMapper<Order> ORDER_ROW_MAPPER = (rs, rowNum) -> {
        User user = new User();
        user.setUser_id(UUID.fromString(rs.getString("user_id")));
        user.setFirstName(rs.getString("first_name"));
        user.setLastName(rs.getString("last_name"));
        user.setEmail(rs.getString("email"));
        user.setCountry(rs.getString("country"));
        user.setCreatedAt(rs.getTimestamp("u_created_at").toLocalDateTime());
        Date lastActive = rs.getDate("u_last_active");
        if (lastActive != null) user.setLastActive(lastActive.toLocalDate());

        Order order = new Order();
        order.setOrder_id(UUID.fromString(rs.getString("order_id")));
        order.setUser(user);
        order.setTotalAmount(rs.getBigDecimal("total_amount"));
        order.setOrderStatus(rs.getString("status"));
        OffsetDateTime odt = rs.getObject("order_date", OffsetDateTime.class);
        order.setOrderDate(odt != null ? odt.toLocalDateTime() : null);
        return order;
    };

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
