package org.learn.repository.lookup;

import org.learn.configuration.lookup.ShardRouter;

import javax.sql.DataSource;
import java.util.OptionalInt;
import java.util.UUID;

/**
 * Lookup-routed shard topology: the shard index comes from the
 * user_data_shard table via ShardRouter. Instantiated only by
 * LookupTableShardingDataSourceConfig — deliberately not component-scanned
 * so there is exactly one registration path for the bean.
 */
public class ShardedDataSource {
    private final DataSource[] shards;
    private final ShardRouter shardRouter;

    public ShardedDataSource(ShardRouter shardRouter, DataSource... shards) {
        this.shards = shards;
        this.shardRouter = shardRouter;
    }

    public int getShardCount() {
        return shards.length;
    }

    public DataSource getDataSourceByIndex(int index) {
        return shards[index];
    }

    /** 0-based shard index, or empty when the user has no routing entry. */
    public OptionalInt findShardIndex(UUID uuid) {
        OptionalInt shardId = shardRouter.findShardIndex(uuid);
        return shardId.isPresent() ? OptionalInt.of(shardId.getAsInt() - 1) : shardId;
    }

    /**
     * 0-based shard index; throws when the user has no routing entry.
     * Use for writes, where routing a user nowhere is a data-integrity error.
     */
    public int getShardIndex(UUID uuid) {
        return findShardIndex(uuid).orElseThrow(() ->
                new IllegalArgumentException("User not found in shard routing table: " + uuid));
    }
}
