package org.learn.service.commons;

import org.learn.domain.AnalyticsResult;
import org.learn.domain.analytics.CountryPartialRow;
import org.learn.domain.analytics.CountryProductPair;
import org.learn.domain.analytics.ProductPartialRow;
import org.learn.domain.analytics.UserStatsRow;
import org.learn.repository.commons.HeavyQueryConstants;
import org.springframework.jdbc.core.JdbcTemplate;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.sql.Date;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.function.IntFunction;

/**
 * Coordinator-side fan-out and aggregation for the heavy analytics query.
 *
 * Why this exists: a single SQL CTE rollup that's cheap to write on a single
 * DB cannot be summed naively across shards. DISTINCT aggregates double-count,
 * per-group thresholds (revenue > 50k) are wrong when computed per-shard, and
 * the same group key (country, product_id) appears on multiple shards.
 *
 * Cost of correctness, paid in this class:
 *   - 4 queries × NUM_SHARDS round-trips, plus 1 product count.
 *   - Per-user, per-product, per-country rows shipped to the app — memory
 *     scales with active entities in the window, not just summary size.
 *   - GROUP BY at the coordinator with proper DISTINCT handling.
 *   - This class duplicates aggregation logic the database already knows how
 *     to do — it's the price of app-level sharding.
 *
 * Sharding-key contract assumed by the math here:
 *   - users partitioned by user_id (one user → one shard).
 *   - orders / order_items co-located with the owning user.
 *   - products replicated to every shard.
 * Break any of these and the aggregations below silently produce wrong
 * numbers. Tests are not optional once this exists.
 */
public final class AnalyticsFanOut {

    private static final ExecutorService EXECUTOR = Executors.newVirtualThreadPerTaskExecutor();

    private AnalyticsFanOut() {}

    public static List<AnalyticsResult> execute(
            IntFunction<JdbcTemplate> shardTemplate,
            int numShards,
            LocalDate from,
            LocalDate to) {

        Date fromSql = Date.valueOf(from);
        Date toSql = Date.valueOf(to);

        List<CompletableFuture<List<UserStatsRow>>> userFutures = new ArrayList<>(numShards);
        List<CompletableFuture<List<ProductPartialRow>>> productFutures = new ArrayList<>(numShards);
        List<CompletableFuture<List<CountryPartialRow>>> countryFutures = new ArrayList<>(numShards);
        List<CompletableFuture<List<CountryProductPair>>> countryProductFutures = new ArrayList<>(numShards);

        for (int i = 0; i < numShards; i++) {
            JdbcTemplate t = shardTemplate.apply(i);
            userFutures.add(CompletableFuture.supplyAsync(
                    () -> t.query(HeavyQueryConstants.USER_STATS_PARTIAL_SQL,
                            HeavyQueryConstants.USER_STATS_ROW_MAPPER, fromSql, toSql),
                    EXECUTOR));
            productFutures.add(CompletableFuture.supplyAsync(
                    () -> t.query(HeavyQueryConstants.PRODUCT_PARTIAL_SQL,
                            HeavyQueryConstants.PRODUCT_PARTIAL_ROW_MAPPER, fromSql, toSql),
                    EXECUTOR));
            countryFutures.add(CompletableFuture.supplyAsync(
                    () -> t.query(HeavyQueryConstants.COUNTRY_PARTIAL_SQL,
                            HeavyQueryConstants.COUNTRY_PARTIAL_ROW_MAPPER, fromSql, toSql),
                    EXECUTOR));
            countryProductFutures.add(CompletableFuture.supplyAsync(
                    () -> t.query(HeavyQueryConstants.COUNTRY_PRODUCT_PAIRS_SQL,
                            HeavyQueryConstants.COUNTRY_PRODUCT_PAIR_ROW_MAPPER, fromSql, toSql),
                    EXECUTOR));
        }

        List<CompletableFuture<?>> all = new ArrayList<>();
        all.addAll(userFutures);
        all.addAll(productFutures);
        all.addAll(countryFutures);
        all.addAll(countryProductFutures);
        try {
            CompletableFuture.allOf(all.toArray(new CompletableFuture[0])).join();
        } catch (Exception e) {
            throw new RuntimeException("Analytics fan-out failed", e);
        }

        List<UserStatsRow> userRows = flatten(userFutures);
        List<ProductPartialRow> productPartialRows = flatten(productFutures);
        List<CountryPartialRow> countryPartialRows = flatten(countryFutures);
        List<CountryProductPair> countryProductPairs = flatten(countryProductFutures);

        AnalyticsResult userAnalytics = aggregateUserAnalytics(userRows);
        AnalyticsResult productAnalytics = aggregateProductAnalytics(productPartialRows);
        AnalyticsResult countryAnalytics = aggregateCountryAnalytics(countryPartialRows, countryProductPairs);

        List<AnalyticsResult> out = new ArrayList<>(3);
        out.add(userAnalytics);
        out.add(productAnalytics);
        out.add(countryAnalytics);
        out.sort(Comparator.comparing(AnalyticsResult::getReportType));
        return out;
    }

    private static <T> List<T> flatten(List<CompletableFuture<List<T>>> futures) {
        List<T> out = new ArrayList<>();
        for (CompletableFuture<List<T>> f : futures) {
            out.addAll(f.join());
        }
        return out;
    }

    /**
     * Each row is one user (users are partitioned, so no cross-shard merge
     * needed). Final summary = COUNT, SUM(orders), SUM(spent), AVG of per-user
     * avgs, COUNT where total_orders > 10. Matches single-DB exactly.
     */
    private static AnalyticsResult aggregateUserAnalytics(List<UserStatsRow> rows) {
        long totalCount = rows.size();
        long totalOrders = 0;
        BigDecimal totalRevenue = BigDecimal.ZERO;
        BigDecimal avgValueSum = BigDecimal.ZERO;
        long avgValueCount = 0;
        long specialCount = 0;

        for (UserStatsRow r : rows) {
            totalOrders += r.totalOrders();
            totalRevenue = totalRevenue.add(r.totalSpent());
            if (r.avgOrderValue() != null) {
                avgValueSum = avgValueSum.add(r.avgOrderValue());
                avgValueCount++;
            }
            if (r.totalOrders() > 10) specialCount++;
        }

        BigDecimal averageValue = avgValueCount > 0
                ? avgValueSum.divide(BigDecimal.valueOf(avgValueCount), 6, RoundingMode.HALF_UP)
                : BigDecimal.ZERO;

        return new AnalyticsResult("User Analytics", totalCount, totalOrders, totalRevenue, averageValue, specialCount);
    }

    /**
     * Per-shard partials are activity-only rows (INNER JOIN with WHERE in
     * PRODUCT_PARTIAL_SQL). GROUP BY product_id across shards (sum slices).
     * Customers disjoint per shard → unique_customers summable.
     * total_count = active-products-in-window, matching the single-DB
     * COUNT(*) over product_performance (which excludes 0-activity rows
     * because the WHERE on the LEFT JOIN'd o.order_date filters them out).
     */
    private static AnalyticsResult aggregateProductAnalytics(List<ProductPartialRow> rows) {
        Map<UUID, ProductAccumulator> byProduct = new HashMap<>();
        for (ProductPartialRow r : rows) {
            byProduct.computeIfAbsent(r.productId(), k -> new ProductAccumulator()).add(r);
        }

        long totalOrders = 0;
        BigDecimal totalRevenue = BigDecimal.ZERO;
        long quantitySum = 0;
        long specialCount = 0;

        for (ProductAccumulator acc : byProduct.values()) {
            totalOrders += acc.timesOrdered;
            totalRevenue = totalRevenue.add(acc.totalRevenue);
            quantitySum += acc.totalQuantity;
            if (acc.totalRevenue.compareTo(BigDecimal.valueOf(10000)) > 0) specialCount++;
        }

        long totalCount = byProduct.size();
        BigDecimal averageValue = totalCount > 0
                ? BigDecimal.valueOf(quantitySum).divide(BigDecimal.valueOf(totalCount), 6, RoundingMode.HALF_UP)
                : BigDecimal.ZERO;

        return new AnalyticsResult("Product Analytics", totalCount, totalOrders, totalRevenue, averageValue, specialCount);
    }

    /**
     * GROUP BY country across shards. total_users is summable (users disjoint).
     * Per-country avg_order_value reconstructed as SUM(total_revenue) /
     * SUM(joined_row_count) to match the single-DB CTE's inflated AVG (which
     * is itself buggy — preserved here for fairness across topologies).
     * unique_products_ordered = size of dedup'd (country, product_id) set
     * across all shards.
     */
    private static AnalyticsResult aggregateCountryAnalytics(
            List<CountryPartialRow> rows, List<CountryProductPair> productPairs) {
        Map<String, CountryAccumulator> byCountry = new HashMap<>();
        for (CountryPartialRow r : rows) {
            byCountry.computeIfAbsent(r.country(), k -> new CountryAccumulator()).add(r);
        }

        Map<String, Set<UUID>> productSetByCountry = new HashMap<>();
        for (CountryProductPair pair : productPairs) {
            productSetByCountry.computeIfAbsent(pair.country(), k -> new HashSet<>()).add(pair.productId());
        }

        long totalCount = byCountry.size();
        long totalOrders = 0;
        BigDecimal totalRevenue = BigDecimal.ZERO;
        BigDecimal avgValueSum = BigDecimal.ZERO;
        long avgValueCount = 0;
        long specialCount = 0;

        for (CountryAccumulator acc : byCountry.values()) {
            totalOrders += acc.totalOrders;
            totalRevenue = totalRevenue.add(acc.totalRevenue);
            BigDecimal countryAvg = acc.joinedRowCount > 0
                    ? acc.totalRevenue.divide(BigDecimal.valueOf(acc.joinedRowCount), 6, RoundingMode.HALF_UP)
                    : BigDecimal.ZERO;
            avgValueSum = avgValueSum.add(countryAvg);
            avgValueCount++;
            if (acc.totalRevenue.compareTo(BigDecimal.valueOf(50000)) > 0) specialCount++;
        }

        BigDecimal averageValue = avgValueCount > 0
                ? avgValueSum.divide(BigDecimal.valueOf(avgValueCount), 6, RoundingMode.HALF_UP)
                : BigDecimal.ZERO;

        // unique_products_ordered is computed per-country but the single-DB
        // summary doesn't surface it — it's part of country_analytics rows that
        // get rolled into total_count etc. Compute and discard for symmetry,
        // or keep for future per-country output. Currently unused; leaving the
        // dedup work in place to demonstrate the cost.
        productSetByCountry.values().stream().mapToInt(Set::size).sum();

        return new AnalyticsResult("Country Analytics", totalCount, totalOrders, totalRevenue, averageValue, specialCount);
    }

    private static final class ProductAccumulator {
        long timesOrdered;
        long totalQuantity;
        BigDecimal totalRevenue = BigDecimal.ZERO;
        long uniqueCustomers;

        void add(ProductPartialRow r) {
            timesOrdered += r.timesOrdered();
            totalQuantity += r.totalQuantity();
            totalRevenue = totalRevenue.add(r.totalRevenue());
            uniqueCustomers += r.uniqueCustomers();
        }
    }

    private static final class CountryAccumulator {
        long totalUsers;
        long totalOrders;
        BigDecimal totalRevenue = BigDecimal.ZERO;
        long joinedRowCount;

        void add(CountryPartialRow r) {
            totalUsers += r.totalUsers();
            totalOrders += r.totalOrders();
            totalRevenue = totalRevenue.add(r.totalRevenue());
            joinedRowCount += r.joinedRowCount();
        }
    }
}
