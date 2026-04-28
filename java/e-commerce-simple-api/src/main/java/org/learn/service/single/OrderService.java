package org.learn.service.single;

import org.learn.domain.Order;
import org.learn.repository.single.OrderRepository;
import org.learn.repository.single.UserRepository;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Profile;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.stereotype.Service;

import java.util.List;
import java.util.Optional;
import java.util.UUID;

@Service
@Profile("single")
public class OrderService implements org.learn.service.OrderService {
    private final OrderRepository orderRepository;
    private final UserRepository userRepository;

    public OrderService(@Autowired  OrderRepository orderRepository, @Autowired UserRepository userRepository){
        this.orderRepository = orderRepository;
        this.userRepository = userRepository;
    }

    public List<Order> getAllOrders(){
        return this.orderRepository.findAll();
    }

    public Page<Order> getAllOrdersWithPaging(PageRequest page){
        return this.orderRepository.findAll(page);
    }

    public Optional<Order> getOrderById(UUID orderId){
        return this.orderRepository.findById(orderId);
    }

    public Optional<List<Order>> getAllOrdersForUserByUuid(UUID userId){
        return this.userRepository.findById(userId).map(user -> this.orderRepository.findByUserId(userId));
    }

}
