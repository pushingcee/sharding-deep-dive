package org.learn.repository.sharded;

import org.learn.domain.User;
import org.learn.repository.commons.UserSql;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Profile;
import org.springframework.dao.EmptyResultDataAccessException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

import java.util.Optional;
import java.util.UUID;

import static org.learn.repository.commons.RowMappers.USER_ROW_MAPPER;

@Profile("sharded")
@Repository
public class UserRepository implements org.learn.repository.UserRepository {

    private final ShardedDataSource shardedDataSource;
    private final JdbcTemplate[] shardTemplates;

    @Autowired
    public UserRepository(ShardedDataSource shardedDataSource) {
        this.shardedDataSource = shardedDataSource;
        this.shardTemplates = new JdbcTemplate[shardedDataSource.getShardCount()];
        for (int i = 0; i < shardTemplates.length; i++) {
            shardTemplates[i] = new JdbcTemplate(shardedDataSource.getDataSourceByIndex(i));
        }
    }

    public Optional<User> findById(UUID userId) {
        JdbcTemplate template = shardTemplates[shardedDataSource.getShardIndex(userId)];
        try {
            return Optional.ofNullable(template.queryForObject(UserSql.FIND_BY_ID, USER_ROW_MAPPER, userId));
        } catch (EmptyResultDataAccessException e) {
            return Optional.empty();
        }
    }
}
