package org.learn.repository;

import org.learn.domain.Order;

import java.time.LocalDateTime;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

public interface OrderRepository {
    Optional<Order> findById(UUID orderId);
    List<Order> findByUserId(UUID userId);
    Order save(Order order);
    List<Order> findPageKeyset(LocalDateTime cursorDate, UUID cursorId, int pageSize);

    /**
     * Deliberately unbounded full-table fetch — this is the OOM/memory-pressure
     * benchmark. It exists to compare how each topology degrades when a query
     * demands the entire orders table at once (one giant scan on a single DB
     * vs four smaller parallel scans on shards). Do NOT "fix" this by adding
     * a limit; the lack of one is the experiment.
     */
    List<Order> findAll();
}
