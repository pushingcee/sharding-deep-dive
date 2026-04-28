package org.learn.domain.product;

import com.fasterxml.jackson.annotation.JsonProperty;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import lombok.Data;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

import java.math.BigDecimal;
import java.util.UUID;

@Data
@Entity(name="products")
public class Product {
    @Id
    @Column(name = "product_id")
    UUID product_id;
    String name;
    String description;
    BigDecimal price;
    String category;
    @JdbcTypeCode(SqlTypes.JSON)
    @Column(name = "technical_specs", columnDefinition = "jsonb")
    @JsonProperty("base_specs")
    BaseSpec baseSpec;

}
