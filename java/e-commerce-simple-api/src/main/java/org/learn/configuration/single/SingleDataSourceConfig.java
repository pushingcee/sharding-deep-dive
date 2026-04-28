package org.learn.configuration.single;

import com.zaxxer.hikari.HikariDataSource;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

import javax.sql.DataSource;

@Profile("single")
@Configuration
public class SingleDataSourceConfig {

    @Bean
    public DataSource singleDataaSource() {
        HikariDataSource ds = new HikariDataSource();
        ds.setJdbcUrl("jdbc:postgresql://localhost:5432/mydb");
        ds.setUsername("postgres");
        ds.setPassword("");
        ds.setDriverClassName("org.postgresql.Driver");
        ds.setMaximumPoolSize(40);
        ds.setMinimumIdle(10);
        ds.setConnectionTimeout(10000);
        ds.setIdleTimeout(300000);
        ds.setPoolName("single-pool");
        return ds;
    }
}
