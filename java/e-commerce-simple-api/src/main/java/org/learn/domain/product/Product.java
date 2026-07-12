package org.learn.domain.product;

import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.Data;

import java.math.BigDecimal;
import java.util.UUID;

@Data
public class Product {
    UUID product_id;
    String name;
    String description;
    BigDecimal price;
    String category;
    @JsonProperty("base_specs")
    BaseSpec baseSpec;
}
