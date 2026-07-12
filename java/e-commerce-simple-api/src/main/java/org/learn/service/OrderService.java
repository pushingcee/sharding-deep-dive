package org.learn.service;

import org.learn.domain.Order;

import java.util.List;
import java.util.Optional;
import java.util.UUID;

public interface OrderService {

    Optional<Order> getOrderById(UUID orderId);

    List<Order> getAllOrdersForUserByUuid(UUID userId);

    /** Cursor-based keyset pagination. cursor=null returns the first page. */
    List<Order> getAllOrdersKeyset(String cursor, int pageSize);
}
