package org.learn.controller;

import org.learn.domain.Order;
import org.learn.service.OrderService;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

@RestController
@RequestMapping("/orders")
public class OrderController {
    private final OrderService orderService;

    public OrderController(@Autowired OrderService orderService) {
        this.orderService = orderService;
    }

    @GetMapping("/user/{uuid}")
    public ResponseEntity<List<Order>> getAllOrdersForUser(@PathVariable UUID uuid) {
        return ResponseEntity.ok(this.orderService.getAllOrdersForUserByUuid(uuid));
    }

    @GetMapping("/{uuid}")
    public ResponseEntity<Order> getOrder(@PathVariable UUID uuid) {
        return this.orderService.getOrderById(uuid)
                .map(ResponseEntity::ok)
                .orElseGet(() -> ResponseEntity.notFound().build());
    }

    /**
     * OOM/memory-pressure benchmark endpoint: fetches EVERY order (joined to
     * its user) with no limit, on purpose. On a full seed this demands the
     * whole orders table at once — one giant scan on the single DB vs four
     * parallel quarter-size scans on the sharded topologies. Expect it to
     * hurt; that is the point. Not part of the Locust workload.
     */
    @GetMapping("/all")
    public ResponseEntity<List<Order>> getAllOrders() {
        return ResponseEntity.ok(this.orderService.getAllOrders());
    }

    /**
     * Keyset-paginated order listing — the same algorithm in every strategy.
     * Response: {"content": [...], "nextCursor": "&lt;order_date&gt;|&lt;order_id&gt;"}.
     * Pass nextCursor back as ?cursor= to fetch the following page; it is
     * omitted on the last page.
     */
    @GetMapping("/all-page")
    public ResponseEntity<Map<String, Object>> getAllOrdersWithPaging(
            @RequestParam(name = "size", defaultValue = "10") int size,
            @RequestParam(name = "cursor", required = false) String cursor) {

        List<Order> content = this.orderService.getAllOrdersKeyset(cursor, size);

        Map<String, Object> body = new LinkedHashMap<>();
        body.put("content", content);
        if (content.size() == size) {
            Order last = content.get(content.size() - 1);
            body.put("nextCursor", last.getOrderDate() + "|" + last.getOrder_id());
        }
        return ResponseEntity.ok(body);
    }
}
