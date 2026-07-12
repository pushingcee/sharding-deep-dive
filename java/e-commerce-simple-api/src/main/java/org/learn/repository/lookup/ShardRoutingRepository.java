package org.learn.repository.lookup;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;

import javax.sql.DataSource;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

/**
 * Routing lookup against the central user_data_shard table. This is the hot
 * path of the lookup architecture — every user-routed request pays this
 * round-trip — so it must not carry extra work (no logging, no per-call
 * object construction) that would inflate the measured routing cost.
 * Failures propagate: a broken routing DB should surface as a 500, not be
 * silently converted into a 404.
 *
 * Instantiated only by LookupTableShardingDataSourceConfig — not
 * component-scanned.
 */
public class ShardRoutingRepository {

    private static final String FIND_SHARD_SQL =
        "SELECT user_id, shard_id FROM user_data_shard WHERE user_id = ?";

    private static final RowMapper<ShardLocation> SHARD_LOCATION_ROW_MAPPER = (rs, rowNum) ->
        new ShardLocation(UUID.fromString(rs.getString("user_id")), rs.getInt("shard_id"));

    private final JdbcTemplate jdbcTemplate;

    public ShardRoutingRepository(DataSource shardRoutingDataSource) {
        this.jdbcTemplate = new JdbcTemplate(shardRoutingDataSource);
    }

    public Optional<ShardLocation> findById(UUID userId) {
        List<ShardLocation> locations = jdbcTemplate.query(FIND_SHARD_SQL, SHARD_LOCATION_ROW_MAPPER, userId);
        return locations.isEmpty() ? Optional.empty() : Optional.of(locations.get(0));
    }
}
