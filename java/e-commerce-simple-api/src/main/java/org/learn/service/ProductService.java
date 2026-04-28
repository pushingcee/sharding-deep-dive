package org.learn.service;

import org.learn.domain.product.Product;

import java.util.List;
import java.util.Optional;
import java.util.UUID;

public interface ProductService {
    public Optional<Product> findByUuid(UUID productId);

    public List<Product> getAllProducts();

}
