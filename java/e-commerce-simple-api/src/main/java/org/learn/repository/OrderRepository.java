package org.learn.repository;

import org.learn.domain.Order;

import java.time.LocalDateTime;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

public interface OrderRepository {
    Optional<Order> findById(UUID orderId);
    List<Order> findAll();
    List<Order> findByUserId(UUID userId);
    Order save(Order order);
    List<Order> findPageKeyset(LocalDateTime cursorDate, UUID cursorId, int pageSize);
}
