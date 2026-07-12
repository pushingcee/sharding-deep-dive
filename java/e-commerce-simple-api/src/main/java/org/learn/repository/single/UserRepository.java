package org.learn.repository.single;

import org.learn.domain.User;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Profile;
import org.springframework.dao.EmptyResultDataAccessException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

import javax.sql.DataSource;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

import static org.learn.repository.commons.RowMappers.USER_ROW_MAPPER;

/**
 * Single-DB user access. Same SQL and JdbcTemplate stack as the sharded and
 * lookup repositories; only the routing differs (none here).
 */
@Profile("single")
@Repository
public class UserRepository implements org.learn.repository.UserRepository {

    private final JdbcTemplate jdbcTemplate;

    @Autowired
    public UserRepository(DataSource dataSource) {
        this.jdbcTemplate = new JdbcTemplate(dataSource);
    }

    public Optional<User> findById(UUID userId) {
        String sql = "SELECT user_id, first_name, last_name, email, country, created_at, last_active FROM users WHERE user_id = ?";
        try {
            return Optional.ofNullable(jdbcTemplate.queryForObject(sql, USER_ROW_MAPPER, userId));
        } catch (EmptyResultDataAccessException e) {
            return Optional.empty();
        }
    }

    public List<User> findAll() {
        String sql = "SELECT user_id, first_name, last_name, email, country, created_at, last_active FROM users";
        return jdbcTemplate.query(sql, USER_ROW_MAPPER);
    }
}
