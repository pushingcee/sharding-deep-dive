package org.learn.domain;

import lombok.Data;

import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.UUID;

@Data
public class Order {
    UUID order_id;
    User user;
    BigDecimal totalAmount;
    String orderStatus;
    LocalDateTime orderDate;
}
