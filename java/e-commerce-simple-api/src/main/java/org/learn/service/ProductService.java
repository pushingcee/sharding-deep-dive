package org.learn.service;

import org.learn.domain.product.Product;

import java.util.Optional;
import java.util.UUID;

public interface ProductService {
    Optional<Product> findByUuid(UUID productId);
}
