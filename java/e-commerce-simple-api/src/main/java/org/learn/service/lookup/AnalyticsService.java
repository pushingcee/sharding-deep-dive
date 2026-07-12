package org.learn.service.lookup;

import org.learn.domain.AnalyticsResult;
import org.learn.repository.lookup.ShardedDataSource;
import org.learn.service.commons.AnalyticsFanOut;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Profile;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

import java.time.LocalDate;
import java.util.List;

@Service
@Profile("lookup")
public class AnalyticsService implements org.learn.service.AnalyticsService {

    private final JdbcTemplate[] shardTemplates;

    public AnalyticsService(@Autowired ShardedDataSource shardedDataSource) {
        this.shardTemplates = new JdbcTemplate[shardedDataSource.getShardCount()];
        for (int i = 0; i < shardTemplates.length; i++) {
            shardTemplates[i] = new JdbcTemplate(shardedDataSource.getDataSourceByIndex(i));
        }
    }

    @Override
    public List<AnalyticsResult> executeHeavyAnalyticsQuery(LocalDate from, LocalDate to) {
        return AnalyticsFanOut.execute(i -> shardTemplates[i], shardTemplates.length, from, to);
    }
}
