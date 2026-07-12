package org.learn.service.single;

import org.learn.domain.AnalyticsResult;
import org.learn.repository.commons.HeavyQueryConstants;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Profile;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

import javax.sql.DataSource;
import java.sql.Date;
import java.time.LocalDate;
import java.util.List;

@Service
@Profile("single")
public class AnalyticsService implements org.learn.service.AnalyticsService {

    private final JdbcTemplate jdbcTemplate;

    public AnalyticsService(@Autowired DataSource dataSource) {
        this.jdbcTemplate = new JdbcTemplate(dataSource);
    }

    @Override
    public List<AnalyticsResult> executeHeavyAnalyticsQuery(LocalDate from, LocalDate to) {
        Date fromSql = Date.valueOf(from);
        Date toSql = Date.valueOf(to);
        return jdbcTemplate.query(
                HeavyQueryConstants.HEAVY_ANALYTICS_QUERY,
                HeavyQueryConstants.ANALYTICS_RESULT_ROW_MAPPER,
                fromSql, toSql, fromSql, toSql, fromSql, toSql);
    }
}
