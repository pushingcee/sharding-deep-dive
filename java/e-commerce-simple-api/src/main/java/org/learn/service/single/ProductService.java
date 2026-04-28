package org.learn.service.single;

import org.learn.domain.product.Product;
import org.learn.repository.single.ProductRepository;
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Service;

import java.util.List;
import java.util.Optional;
import java.util.UUID;

@Service
@Profile("single")
public class ProductService implements org.learn.service.ProductService {
    private final ProductRepository productRepository;

    public ProductService(ProductRepository productRepository) {
        this.productRepository = productRepository;
    }

    public Optional<Product> findByUuid(UUID product_uuid) {
        return this.productRepository.findById(product_uuid);
    }

    @Override
    public List<Product> getAllProducts() {
        return List.of();
    }
}
