package org.learn.repository;

import org.learn.domain.product.Product;

import java.util.List;
import java.util.Optional;
import java.util.UUID;

public interface ProductRepository {
    Optional<Product> findById(UUID productId);
    List<Product> findAll();
}
