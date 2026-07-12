package org.learn.service.commons;

import org.learn.domain.product.Product;
import org.learn.repository.ProductRepository;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Service;

import java.util.Optional;
import java.util.UUID;

@Service
@Profile({"single", "sharded", "lookup"})
public class ProductService implements org.learn.service.ProductService {
    private final ProductRepository productRepository;

    public ProductService(@Autowired ProductRepository productRepository) {
        this.productRepository = productRepository;
    }

    public Optional<Product> findByUuid(UUID productId) {
        return productRepository.findById(productId);
    }
}
