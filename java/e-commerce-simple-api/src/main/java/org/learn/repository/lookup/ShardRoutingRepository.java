package org.learn.repository.lookup;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Profile;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.stereotype.Repository;

import javax.sql.DataSource;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

@Profile("lookup")
@Repository
public class ShardRoutingRepository {

    private final DataSource shardRoutingDataSource;

    @Autowired
    public ShardRoutingRepository(DataSource shardRoutingDataSource) {
        this.shardRoutingDataSource = shardRoutingDataSource;
    }

    RowMapper<ShardLocation> shardLocationRowMapper = (rs, rowNum) -> {
        UUID user_id = UUID.fromString(rs.getString("user_id"));
        int shard_id = rs.getInt("shard_id");
        return new ShardLocation(user_id, shard_id);
    };


    public Optional<ShardLocation> findById(UUID userId) {
        JdbcTemplate jdbcTemplate = new JdbcTemplate(shardRoutingDataSource);

        try {
            String sql = "SELECT user_id, shard_id FROM user_data_shard WHERE user_id = ?";
            System.out.println("User id:" + userId);
            List<ShardLocation> users = jdbcTemplate.query(sql, shardLocationRowMapper, userId);

            if (!users.isEmpty()) {
                return Optional.of(users.get(0));
            }
        } catch (Exception e) {
            System.err.println("Error finding user by ID: " + e.getMessage());
        }
        return Optional.empty();
    }
}
