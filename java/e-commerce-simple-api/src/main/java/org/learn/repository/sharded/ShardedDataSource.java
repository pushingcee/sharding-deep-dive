package org.learn.repository.sharded;

import org.learn.configuration.sharded.ShardRouter;
import org.springframework.context.annotation.Profile;

import javax.sql.DataSource;
import java.util.UUID;

@Profile("sharded")
public class ShardedDataSource {
    private final ShardRouter shardRouter;
    private final DataSource[] shards;
    private final DataSource defaultDataSource;

    public ShardedDataSource(ShardRouter shardRouter, DataSource... shards) {
        this.shardRouter = shardRouter;
        this.shards = shards;
        this.defaultDataSource = shards[0];
    }

    public DataSource getDataSource(){
        return defaultDataSource;
    }

    public DataSource getDataSourceByIndex(int index){
        return shards[index];
    }

    public DataSource getDataSource(UUID user_uuid){
        int shardIndex = shardRouter.getShardIndex(user_uuid);
        return shards[shardIndex];
    }

    public DataSource getDataSource(String user_uuid){
        int shardIndex = shardRouter.getShardIndex(user_uuid);
        return shards[shardIndex];
    }

    public int getShardIndex(UUID user_uuid) {
        return shardRouter.getShardIndex(user_uuid);
    }

    public int getShardIndex(String user_uuid) {
        return shardRouter.getShardIndex(user_uuid);
    }
}
