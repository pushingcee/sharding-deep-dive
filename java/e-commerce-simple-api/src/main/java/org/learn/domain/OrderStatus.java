package org.learn.domain;

import com.fasterxml.jackson.annotation.JsonProperty;

public enum OrderStatus {
    @JsonProperty("shipped")
    SHIPPED,
    @JsonProperty("cancelled")
    CANCELLED,
    @JsonProperty("pending")
    PENDING,
    @JsonProperty("delivered")
    DELIVERED

}
