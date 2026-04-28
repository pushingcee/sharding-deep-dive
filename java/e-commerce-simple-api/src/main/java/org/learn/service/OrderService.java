package org.learn.service;

import org.learn.domain.Order;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;

import java.util.List;
import java.util.Optional;
import java.util.UUID;

public interface OrderService {

    List<Order> getAllOrders();

    Page<Order> getAllOrdersWithPaging(PageRequest page);

    Optional<Order> getOrderById(UUID orderId);

    Optional<List<Order>> getAllOrdersForUserByUuid(UUID userId);

    /** Cursor-based keyset pagination. cursor=null returns the first page. */
    default List<Order> getAllOrdersKeyset(String cursor, int pageSize) {
        throw new UnsupportedOperationException("Keyset pagination not supported for this mode");
    }
}
