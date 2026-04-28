package org.learn.domain.analytics;

import java.math.BigDecimal;

public record UserStatsRow(long totalOrders, BigDecimal totalSpent, BigDecimal avgOrderValue) {}
