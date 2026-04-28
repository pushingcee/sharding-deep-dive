package org.learn.domain.analytics;

import java.math.BigDecimal;

public record CountryPartialRow(
        String country,
        long totalUsers,
        long totalOrders,
        BigDecimal totalRevenue,
        long joinedRowCount
) {}
