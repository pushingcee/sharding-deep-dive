package org.learn.repository.single;

import org.learn.domain.product.Product;
import org.springframework.context.annotation.Profile;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.UUID;

@Profile("single")
public interface ProductRepository extends JpaRepository<Product, UUID> {
}
