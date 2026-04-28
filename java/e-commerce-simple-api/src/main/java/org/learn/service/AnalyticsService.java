package org.learn.service;

import org.learn.domain.AnalyticsResult;

import java.time.LocalDate;
import java.util.List;

public interface AnalyticsService {
    List<AnalyticsResult> executeHeavyAnalyticsQuery(LocalDate from, LocalDate to);
}
