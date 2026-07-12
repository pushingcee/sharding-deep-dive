package org.learn.repository.single;

import org.learn.domain.User;
import org.learn.repository.commons.UserSql;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Profile;
import org.springframework.dao.EmptyResultDataAccessException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

import javax.sql.DataSource;
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
        try {
            return Optional.ofNullable(jdbcTemplate.queryForObject(UserSql.FIND_BY_ID, USER_ROW_MAPPER, userId));
        } catch (EmptyResultDataAccessException e) {
            return Optional.empty();
        }
    }
}
