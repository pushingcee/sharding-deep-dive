package org.learn.repository.single;

import org.learn.domain.Order;
import org.learn.repository.commons.OrderSql;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Profile;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

import javax.sql.DataSource;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

import static org.learn.repository.commons.RowMappers.ORDER_ROW_MAPPER;

/**
 * Single-DB order access. Runs the exact same SQL (OrderSql) through the same
 * JdbcTemplate stack as the sharded/lookup repositories — the only difference
 * is that there is one target database and no routing/fan-out. Keeping the
 * stacks identical is what lets the benchmark attribute latency differences
 * to the architecture above the database instead of to JPA-vs-JDBC noise.
 */
@Profile("single")
@Repository
public class OrderRepository implements org.learn.repository.OrderRepository {

    private final JdbcTemplate jdbcTemplate;

    @Autowired
    public OrderRepository(DataSource dataSource) {
        this.jdbcTemplate = new JdbcTemplate(dataSource);
    }

    public Optional<Order> findById(UUID orderId) {
        List<Order> orders = jdbcTemplate.query(OrderSql.FIND_BY_ID, ORDER_ROW_MAPPER, orderId);
        return orders.isEmpty() ? Optional.empty() : Optional.of(orders.get(0));
    }

    public List<Order> findByUserId(UUID userId) {
        return jdbcTemplate.query(OrderSql.FIND_BY_USER_ID, ORDER_ROW_MAPPER, userId);
    }

    public List<Order> findAll() {
        return jdbcTemplate.query(OrderSql.FIND_ALL, ORDER_ROW_MAPPER);
    }

    public List<Order> findPageKeyset(LocalDateTime cursorDate, UUID cursorId, int pageSize) {
        if (cursorDate == null) {
            return jdbcTemplate.query(OrderSql.PAGE_KEYSET_FIRST, ORDER_ROW_MAPPER, pageSize);
        }
        return jdbcTemplate.query(OrderSql.PAGE_KEYSET_NEXT, ORDER_ROW_MAPPER,
                cursorDate, cursorDate, cursorId, pageSize);
    }

    public Order save(Order order) {
        if (order.getOrder_id() == null) {
            LocalDateTime orderDate = order.getOrderDate() != null ? order.getOrderDate() : LocalDateTime.now();
            jdbcTemplate.update(OrderSql.INSERT,
                    UUID.randomUUID(), order.getUser().getUser_id(), orderDate,
                    order.getTotalAmount(), order.getOrderStatus());
        } else {
            jdbcTemplate.update(OrderSql.UPDATE,
                    order.getUser().getUser_id(), order.getTotalAmount(),
                    order.getOrderStatus(), order.getOrder_id());
        }
        return order;
    }
}
