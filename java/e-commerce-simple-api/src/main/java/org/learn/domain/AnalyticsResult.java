package org.learn.domain;

import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.math.BigDecimal;

@Data
@NoArgsConstructor
@AllArgsConstructor
public class AnalyticsResult {
    private String reportType;
    private Long totalCount;
    private Long totalOrders;
    private BigDecimal totalRevenue;
    private BigDecimal averageValue;
    private Long specialCount;
}