package org.learn.repository.lookup;

import org.learn.configuration.lookup.ShardRouter;
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;

import javax.sql.DataSource;
import java.util.UUID;

@Profile("lookup")
@Component
public class ShardedDataSource {
    private final DataSource[] shards;
    private final ShardRouter shardRouter;
    public ShardedDataSource(ShardRouter shardRouter, DataSource... shards) {
        this.shards = shards;
        this.shardRouter = shardRouter;
    }


    public DataSource getDataSource(UUID uuid){
        return shards[getShardIndex(uuid)];
    }

    /** 0-based shard index; the lookup table stores shard_id 1-based. */
    public int getShardIndex(UUID uuid){
        return shardRouter.getShardIndex(uuid) - 1;
    }

    public DataSource getDataSourceByIndex(int index){
        return shards[index];
    }
}
