package org.learn.repository.sharded;

import org.learn.domain.Order;
import org.learn.domain.User;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Profile;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.stereotype.Repository;

import java.sql.Date;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

@Profile("sharded")
@Repository
public class OrderRepository implements org.learn.repository.OrderRepository {

    private static final int NUM_SHARDS = 4;
    private static final ExecutorService VIRTUAL_EXECUTOR = Executors.newVirtualThreadPerTaskExecutor();

    private static final String ORDER_COLS =
        "o.order_id, o.user_id, o.total_amount, o.status, o.order_date, " +
        "u.first_name, u.last_name, u.email, u.country, " +
        "u.created_at AS u_created_at, u.last_active AS u_last_active";

    private static final String FROM_ORDERS_JOIN_USERS =
        " FROM orders o JOIN users u ON o.user_id = u.user_id";

    private static final RowMapper<Order> ORDER_ROW_MAPPER = (rs, _) -> {
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

    private final ShardedDataSource shardedDataSource;
    private final JdbcTemplate[] shardTemplates;

    @Autowired
    public OrderRepository(ShardedDataSource shardedDataSource) {
        this.shardedDataSource = shardedDataSource;
        this.shardTemplates = new JdbcTemplate[NUM_SHARDS];
        for (int i = 0; i < NUM_SHARDS; i++) {
            this.shardTemplates[i] = new JdbcTemplate(shardedDataSource.getDataSourceByIndex(i));
        }
    }

    public List<Order> findPageKeyset(LocalDateTime cursorDate, UUID cursorId, int pageSize) {
        List<CompletableFuture<List<Order>>> futures = new ArrayList<>();

        for (int i = 0; i < NUM_SHARDS; i++) {
            JdbcTemplate template = shardTemplates[i];
            futures.add(CompletableFuture.supplyAsync(() -> {
                if (cursorDate == null) {
                    String sql = "SELECT " + ORDER_COLS + FROM_ORDERS_JOIN_USERS +
                                 " ORDER BY o.order_date DESC, o.order_id DESC LIMIT ?";
                    return template.query(sql, ORDER_ROW_MAPPER, pageSize);
                } else {
                    String sql = "SELECT " + ORDER_COLS + FROM_ORDERS_JOIN_USERS +
                                 " WHERE o.order_date < ? OR (o.order_date = ? AND o.order_id < ?)" +
                                 " ORDER BY o.order_date DESC, o.order_id DESC LIMIT ?";
                    return template.query(sql, ORDER_ROW_MAPPER, cursorDate, cursorDate, cursorId, pageSize);
                }
            }, VIRTUAL_EXECUTOR));
        }

        CompletableFuture.allOf(futures.toArray(new CompletableFuture[0])).join();

        List<Order> merged = new ArrayList<>(pageSize * NUM_SHARDS);
        for (CompletableFuture<List<Order>> future : futures) {
            merged.addAll(future.join());
        }

        merged.sort(Comparator
            .comparing(Order::getOrderDate, Comparator.nullsLast(Comparator.reverseOrder()))
            .thenComparing(Order::getOrder_id, Comparator.nullsLast(Comparator.reverseOrder())));

        return merged.size() > pageSize ? merged.subList(0, pageSize) : merged;
    }

    public Optional<Order> findById(UUID orderId) {
        String sql = "SELECT " + ORDER_COLS + FROM_ORDERS_JOIN_USERS + " WHERE o.order_id = ?";
        List<CompletableFuture<Optional<Order>>> futures = new ArrayList<>();

        for (int i = 0; i < NUM_SHARDS; i++) {
            JdbcTemplate template = shardTemplates[i];
            futures.add(CompletableFuture.supplyAsync(() -> {
                List<Order> orders = template.query(sql, ORDER_ROW_MAPPER, orderId);
                return orders.isEmpty() ? Optional.<Order>empty() : Optional.of(orders.get(0));
            }, VIRTUAL_EXECUTOR));
        }

        CompletableFuture.allOf(futures.toArray(new CompletableFuture[0])).join();

        for (CompletableFuture<Optional<Order>> future : futures) {
            Optional<Order> result = future.join();
            if (result.isPresent()) return result;
        }

        return Optional.empty();
    }

    public List<Order> findAll() {
        String sql = "SELECT " + ORDER_COLS + FROM_ORDERS_JOIN_USERS;
        List<CompletableFuture<List<Order>>> futures = new ArrayList<>();

        for (int i = 0; i < NUM_SHARDS; i++) {
            JdbcTemplate template = shardTemplates[i];
            futures.add(CompletableFuture.supplyAsync(
                () -> template.query(sql, ORDER_ROW_MAPPER),
                VIRTUAL_EXECUTOR
            ));
        }

        CompletableFuture.allOf(futures.toArray(new CompletableFuture[0])).join();

        List<Order> allOrders = new ArrayList<>();
        for (CompletableFuture<List<Order>> future : futures) {
            allOrders.addAll(future.join());
        }
        return allOrders;
    }

    public List<Order> findByUserId(UUID userId) {
        JdbcTemplate template = shardTemplates[shardedDataSource.getShardIndex(userId)];
        String sql = "SELECT " + ORDER_COLS + FROM_ORDERS_JOIN_USERS + " WHERE o.user_id = ?";
        return template.query(sql, ORDER_ROW_MAPPER, userId);
    }

    public Order save(Order order) {
        JdbcTemplate template = shardTemplates[shardedDataSource.getShardIndex(order.getUser().getUser_id())];

        if (order.getOrder_id() == null) {
            template.update("INSERT INTO orders (order_id, user_id, total_amount, status) VALUES (?, ?, ?, ?)",
                    UUID.randomUUID(), order.getUser().getUser_id(),
                    order.getTotalAmount(), order.getOrderStatus());
        } else {
            template.update("UPDATE orders SET user_id = ?, total_amount = ?, status = ? WHERE order_id = ?",
                    order.getUser().getUser_id(), order.getTotalAmount(),
                    order.getOrderStatus(), order.getOrder_id());
        }
        return order;
    }
}
