package org.learn.controller;

import org.learn.domain.Order;
import org.learn.service.OrderService;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Optional;
import java.util.UUID;

@RestController
@RequestMapping("/orders")
public class OrderController {
    private final OrderService orderService;

    public OrderController(@Autowired OrderService userService){
        this.orderService = userService;
    }

    @GetMapping("/user/{uuid}")
    public ResponseEntity<List<Order>> getAllOrdersForUser(@PathVariable UUID uuid){
        Optional<List<Order>> orderOptionalList = this.orderService.getAllOrdersForUserByUuid(uuid);

        return orderOptionalList
                .map(ResponseEntity::ok)
                .orElseGet(() -> ResponseEntity.notFound().build());
    }

    @GetMapping("/{uuid}")
    public ResponseEntity<Order> getProduct(@PathVariable UUID uuid){
        Optional<Order> orderoptional = this.orderService.getOrderById(uuid);

        return orderoptional
                .map(ResponseEntity::ok)
                .orElseGet(() -> ResponseEntity.notFound().build());
    }

    @GetMapping("/all")
    public ResponseEntity<List<Order>> getAllOrders(){
        List<Order> orderList = this.orderService.getAllOrders();

        return ResponseEntity.ok(
                orderList
        );
    }

    @GetMapping("/all-page")
    public ResponseEntity<?> getAllOrdersWithPaging(
            @RequestParam(name="page", defaultValue = "0", required = false) int pageNumber,
            @RequestParam(name="size", defaultValue = "10", required = false) int size,
            @RequestParam(name="cursor", required = false) String cursor) {

        // cursor present → explicit keyset request
        if (cursor != null) {
            try {
                List<Order> content = this.orderService.getAllOrdersKeyset(cursor, size);
                return ResponseEntity.ok(java.util.Map.of("content", content));
            } catch (UnsupportedOperationException e) {
                return ResponseEntity.badRequest().body("Keyset pagination not supported for this mode");
            }
        }

        // no cursor → offset pagination (single/citus) or keyset first page (sharded, via getAllOrdersWithPaging)
        PageRequest page = PageRequest.of(pageNumber, size, Sort.Direction.ASC, "orderStatus");
        Page<Order> orderList = this.orderService.getAllOrdersWithPaging(page);
        return ResponseEntity.ok(orderList);
    }
}
