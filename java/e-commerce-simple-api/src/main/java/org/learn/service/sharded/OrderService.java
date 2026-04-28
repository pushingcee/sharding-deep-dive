package org.learn.service.sharded;

import org.learn.domain.Order;
import org.learn.repository.OrderRepository;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Profile;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageImpl;
import org.springframework.data.domain.PageRequest;
import org.springframework.stereotype.Service;

import java.time.LocalDateTime;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

@Service
@Profile({"sharded", "lookup"})
public class OrderService implements org.learn.service.OrderService {
    private final OrderRepository orderRepository;

    @Autowired
    public OrderService(OrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    public Optional<Order> getOrderById(UUID orderId) {
        return orderRepository.findById(orderId);
    }

    public List<Order> getAllOrders() {
        return orderRepository.findAll();
    }

    @Override
    public Page<Order> getAllOrdersWithPaging(PageRequest page) {
        List<Order> content = getAllOrdersKeyset(null, page.getPageSize());
        return new PageImpl<>(content, page, Long.MAX_VALUE);
    }

    @Override
    public List<Order> getAllOrdersKeyset(String cursor, int pageSize) {
        LocalDateTime cursorDate = null;
        UUID cursorId = null;

        if (cursor != null && !cursor.isBlank()) {
            String[] parts = cursor.split("\\|");
            cursorDate = LocalDateTime.parse(parts[0]);
            cursorId = UUID.fromString(parts[1]);
        }

        return orderRepository.findPageKeyset(cursorDate, cursorId, pageSize);
    }

    public Optional<List<Order>> getAllOrdersForUserByUuid(UUID userId) {
        return Optional.of(orderRepository.findByUserId(userId));
    }
} 