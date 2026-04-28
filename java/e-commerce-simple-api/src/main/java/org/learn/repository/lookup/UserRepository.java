package org.learn.repository.lookup;

import org.learn.domain.User;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Profile;
import org.springframework.dao.EmptyResultDataAccessException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

import javax.sql.DataSource;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

import static org.learn.repository.commons.RowMappers.USER_ROW_MAPPER;

@Profile("lookup")
@Repository
public class UserRepository implements org.learn.repository.UserRepository {

    private final ShardedDataSource shardedDataSource;

    @Autowired
    public UserRepository(ShardedDataSource shardedDataSource) {
        this.shardedDataSource = shardedDataSource;
    }

    public Optional<User> findById(UUID userId) {
        DataSource shardDataSource = shardedDataSource.getDataSource(userId);
        JdbcTemplate jdbcTemplate = new JdbcTemplate(shardDataSource);
        String sql = "SELECT user_id, first_name, last_name, email, country, created_at, last_active FROM users WHERE user_id = ?";
        try {
            return Optional.ofNullable(jdbcTemplate.queryForObject(sql, USER_ROW_MAPPER, userId));
        } catch (EmptyResultDataAccessException e) {
            return Optional.empty();
        }
    }

    public List<User> findAll() {
        List<java.util.concurrent.CompletableFuture<List<User>>> futures = new ArrayList<>();

        for (int i = 0; i < 4; i++) { // Assuming 4 shards
            int finalShardIndex = i;
            futures.add(java.util.concurrent.CompletableFuture.supplyAsync(() -> {
                DataSource shardDataSource = shardedDataSource.getDataSourceByIndex(finalShardIndex);
                JdbcTemplate jdbcTemplate = new JdbcTemplate(shardDataSource);
                String sql = "SELECT user_id, first_name, last_name, email, country, created_at, last_active FROM users";
                return jdbcTemplate.query(sql, USER_ROW_MAPPER);
            }));
        }

        java.util.concurrent.CompletableFuture.allOf(futures.toArray(new java.util.concurrent.CompletableFuture[0]))
                .join();

        List<User> allUsers = new ArrayList<>();
        for (java.util.concurrent.CompletableFuture<List<User>> future : futures) {
            allUsers.addAll(future.join());
        }

        return allUsers;
    }

    public List<User> findByCountry(String country) {
        List<java.util.concurrent.CompletableFuture<List<User>>> futures = new ArrayList<>();

        for (int i = 0; i < 4; i++) { // Assuming 4 shards
            int finalShardIndex = i;
            futures.add(java.util.concurrent.CompletableFuture.supplyAsync(() -> {
                DataSource shardDataSource = shardedDataSource.getDataSourceByIndex(finalShardIndex);
                JdbcTemplate jdbcTemplate = new JdbcTemplate(shardDataSource);
                String sql = "SELECT user_id, first_name, last_name, email, country, created_at, last_active FROM users WHERE country = ?";
                return jdbcTemplate.query(sql, USER_ROW_MAPPER, country);
            }));
        }

        java.util.concurrent.CompletableFuture.allOf(futures.toArray(new java.util.concurrent.CompletableFuture[0]))
                .join();

        List<User> usersByCountry = new ArrayList<>();
        for (java.util.concurrent.CompletableFuture<List<User>> future : futures) {
            usersByCountry.addAll(future.join());
        }

        return usersByCountry;
    }
}
