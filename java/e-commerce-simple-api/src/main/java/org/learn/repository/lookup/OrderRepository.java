package org.learn.repository.lookup;

import org.learn.domain.Order;
import org.learn.repository.commons.OrderSql;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Profile;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

import static org.learn.repository.commons.RowMappers.ORDER_ROW_MAPPER;

/**
 * Lookup-table order access. Structurally identical to the sharded
 * repository (same SQL, same cached templates, same fan-out) — the only
 * intended difference is that shard routing goes through the lookup DB
 * (ShardRouter → user_data_shard) instead of hashing the UUID.
 */
@Profile("lookup")
@Repository
public class OrderRepository implements org.learn.repository.OrderRepository {

    private static final int NUM_SHARDS = 4;
    private static final ExecutorService VIRTUAL_EXECUTOR = Executors.newVirtualThreadPerTaskExecutor();

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
                    return template.query(OrderSql.PAGE_KEYSET_FIRST, ORDER_ROW_MAPPER, pageSize);
                } else {
                    return template.query(OrderSql.PAGE_KEYSET_NEXT, ORDER_ROW_MAPPER,
                            cursorDate, cursorDate, cursorId, pageSize);
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
        List<CompletableFuture<Optional<Order>>> futures = new ArrayList<>();

        for (int i = 0; i < NUM_SHARDS; i++) {
            JdbcTemplate template = shardTemplates[i];
            futures.add(CompletableFuture.supplyAsync(() -> {
                List<Order> orders = template.query(OrderSql.FIND_BY_ID, ORDER_ROW_MAPPER, orderId);
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
        List<CompletableFuture<List<Order>>> futures = new ArrayList<>();

        for (int i = 0; i < NUM_SHARDS; i++) {
            JdbcTemplate template = shardTemplates[i];
            futures.add(CompletableFuture.supplyAsync(
                () -> template.query(OrderSql.FIND_ALL, ORDER_ROW_MAPPER),
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
        return template.query(OrderSql.FIND_BY_USER_ID, ORDER_ROW_MAPPER, userId);
    }

    public Order save(Order order) {
        JdbcTemplate template = shardTemplates[shardedDataSource.getShardIndex(order.getUser().getUser_id())];

        if (order.getOrder_id() == null) {
            template.update(OrderSql.INSERT,
                    UUID.randomUUID(), order.getUser().getUser_id(),
                    order.getTotalAmount(), order.getOrderStatus());
        } else {
            template.update(OrderSql.UPDATE,
                    order.getUser().getUser_id(), order.getTotalAmount(),
                    order.getOrderStatus(), order.getOrder_id());
        }
        return order;
    }
}
