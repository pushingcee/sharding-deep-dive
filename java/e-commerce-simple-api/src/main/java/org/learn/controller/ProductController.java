package org.learn.controller;

import org.learn.domain.product.Product;
import org.learn.service.ProductService;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Optional;
import java.util.UUID;

@RestController
@RequestMapping("/products")
public class ProductController {
    private final ProductService productService;

    public ProductController(@Autowired ProductService userService){
        this.productService = userService;
    }

    @GetMapping("/{uuid}")
    public ResponseEntity<Product> getProduct(@PathVariable UUID uuid){
        Optional<Product> productOptional = this.productService.findByUuid(uuid);

        return productOptional
                .map(ResponseEntity::ok)
                .orElseGet(() -> ResponseEntity.notFound().build());
    }
}
