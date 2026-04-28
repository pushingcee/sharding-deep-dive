package org.learn.configuration.lookup;

import com.zaxxer.hikari.HikariDataSource;
import org.learn.repository.lookup.ShardRoutingRepository;
import org.learn.repository.lookup.ShardedDataSource;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

import javax.sql.DataSource;

@Profile("lookup")
@Configuration
public class LookupTableShardingDataSourceConfig {

    @Bean
    public ShardedDataSource shardedDataSource() {
        return new ShardedDataSource(
                getShardRouter(),
                createShardDataSource(5433, "lookup-shard-1-pool"),
                createShardDataSource(5434, "lookup-shard-2-pool"),
                createShardDataSource(5435, "lookup-shard-3-pool"),
                createShardDataSource(5436, "lookup-shard-4-pool")
        );
    }

    @Bean
    public DataSource getLookupDb() {
        HikariDataSource ds = new HikariDataSource();
        ds.setJdbcUrl("jdbc:postgresql://localhost:5432/mydb");
        ds.setUsername("postgres");
        ds.setPassword("");
        ds.setDriverClassName("org.postgresql.Driver");
        ds.setMaximumPoolSize(40);
        ds.setMinimumIdle(10);
        ds.setConnectionTimeout(10000);
        ds.setIdleTimeout(300000);
        ds.setPoolName("lookup-routing-pool");
        return ds;
    }

    @Bean
    public ShardRouter getShardRouter() {
        return new ShardRouter(getShardRoutingRepository());
    }

    @Bean
    public ShardRoutingRepository getShardRoutingRepository() {
        return new ShardRoutingRepository(getLookupDb());
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
}
