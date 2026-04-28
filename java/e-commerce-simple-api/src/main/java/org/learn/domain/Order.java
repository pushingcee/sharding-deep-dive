package org.learn.domain;

import jakarta.persistence.*;
import lombok.Data;

import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.UUID;

@Data
@Entity(name = "orders")
public class Order {
    @Id
    @GeneratedValue
    @Column(name = "order_id")
    UUID order_id;
    @ManyToOne(fetch = FetchType.EAGER)
    @JoinColumn(name = "user_id")
    User user;
    BigDecimal totalAmount;
    @Column(name = "status", columnDefinition = "varchar(20)")
    String orderStatus;
    @Column(name = "order_date")
    LocalDateTime orderDate;
}
