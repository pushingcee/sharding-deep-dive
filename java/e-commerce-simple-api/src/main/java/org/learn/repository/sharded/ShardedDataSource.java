package org.learn.repository.sharded;

import org.learn.configuration.sharded.ShardRouter;

import javax.sql.DataSource;
import java.util.UUID;

/**
 * Hash-routed shard topology: the shard index is computed from the user UUID,
 * no external lookup. Instantiated only by ManualShardingDataSourceConfig —
 * deliberately not component-scanned so there is exactly one registration
 * path for the bean.
 */
public class ShardedDataSource {
    private final ShardRouter shardRouter;
    private final DataSource[] shards;

    public ShardedDataSource(ShardRouter shardRouter, DataSource... shards) {
        this.shardRouter = shardRouter;
        this.shards = shards;
    }

    public int getShardCount() {
        return shards.length;
    }

    public DataSource getDataSourceByIndex(int index) {
        return shards[index];
    }

    public int getShardIndex(UUID userUuid) {
        return shardRouter.getShardIndex(userUuid);
    }
}
