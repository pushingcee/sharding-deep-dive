package org.learn.repository.single;

import org.learn.domain.Order;
import org.springframework.context.annotation.Profile;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.util.List;
import java.util.UUID;

@Profile("single")
public interface OrderRepository extends JpaRepository<Order, UUID> {
    @Query("SELECT o FROM orders o WHERE o.user.user_id=:userId")
    public List<Order> findByUserId(@Param("userId") UUID userId);
}
