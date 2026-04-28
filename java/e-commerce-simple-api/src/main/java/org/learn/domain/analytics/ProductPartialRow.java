package org.learn.domain.analytics;

import java.math.BigDecimal;
import java.util.UUID;

public record ProductPartialRow(
        UUID productId,
        long timesOrdered,
        long totalQuantity,
        BigDecimal totalRevenue,
        long uniqueCustomers
) {}
