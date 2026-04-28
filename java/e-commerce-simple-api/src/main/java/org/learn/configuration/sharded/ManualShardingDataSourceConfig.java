package org.learn.configuration.sharded;

import com.zaxxer.hikari.HikariDataSource;
import org.learn.repository.sharded.ShardedDataSource;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;
import org.springframework.context.annotation.Profile;

import javax.sql.DataSource;

@Profile("sharded")
@Configuration
public class ManualShardingDataSourceConfig {

    @Bean
    @Primary
    public ShardedDataSource shardedDataSource() {
        return new ShardedDataSource(
                shardRouter(),
                createShardDataSource(5433, "shard-1-pool"),
                createShardDataSource(5434, "shard-2-pool"),
                createShardDataSource(5435, "shard-3-pool"),
                createShardDataSource(5436, "shard-4-pool"));
    }

    private DataSource createShardDataSource(int port, String poolName) {
        HikariDataSource ds = new HikariDataSource();
        ds.setJdbcUrl("jdbc:postgresql://localhost:" + port + "/mydb");
        ds.setUsername("postgres");
        ds.setPassword("");
        ds.setDriverClassName("org.postgresql.Driver");
        ds.setMaximumPoolSize(40);
        ds.setMinimumIdle(5);
        ds.setConnectionTimeout(10000);
        ds.setIdleTimeout(300000);
        ds.setPoolName(poolName);
        return ds;
    }

    @Bean
    public ShardRouter shardRouter() {
        return new ShardRouter();
    }
}
