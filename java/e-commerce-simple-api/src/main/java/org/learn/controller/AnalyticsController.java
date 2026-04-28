package org.learn.controller;

import org.learn.domain.AnalyticsResult;
import org.learn.service.AnalyticsService;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.time.LocalDate;
import java.util.List;

@RestController
@RequestMapping("/analytics")
public class AnalyticsController {

    private final AnalyticsService analyticsService;

    public AnalyticsController(@Autowired AnalyticsService analyticsService) {
        this.analyticsService = analyticsService;
    }

    @GetMapping
    public ResponseEntity<List<AnalyticsResult>> executeHeavyQuery(
            @RequestParam(name = "from", required = false)
            @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) LocalDate from,
            @RequestParam(name = "to", required = false)
            @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) LocalDate to) {

        LocalDate effectiveTo = (to != null) ? to : LocalDate.now();
        LocalDate effectiveFrom = (from != null) ? from : effectiveTo.minusMonths(6);

        long startTime = System.currentTimeMillis();
        List<AnalyticsResult> results = analyticsService.executeHeavyAnalyticsQuery(effectiveFrom, effectiveTo);
        long executionTime = System.currentTimeMillis() - startTime;

        return ResponseEntity.ok()
                .header("X-Execution-Time-Ms", String.valueOf(executionTime))
                .header("X-Analytics-From", effectiveFrom.toString())
                .header("X-Analytics-To", effectiveTo.toString())
                .body(results);
    }
}
