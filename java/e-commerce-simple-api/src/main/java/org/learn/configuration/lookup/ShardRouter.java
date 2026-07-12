package org.learn.configuration.lookup;

import org.learn.repository.lookup.ShardRoutingRepository;

import java.util.OptionalInt;
import java.util.UUID;

/**
 * Routing via the central lookup table. Returns the 1-based shard_id stored
 * in user_data_shard, or empty when the user has no routing entry — callers
 * decide whether a miss is a not-found (reads) or an error (writes).
 * Instantiated only by LookupTableShardingDataSourceConfig — not
 * component-scanned.
 */
public class ShardRouter {
    private final ShardRoutingRepository shardRoutingRepository;

    public ShardRouter(ShardRoutingRepository shardRoutingRepository) {
        this.shardRoutingRepository = shardRoutingRepository;
    }

    public OptionalInt findShardIndex(UUID userId) {
        return shardRoutingRepository.findById(userId)
                .map(location -> OptionalInt.of(location.shard_id()))
                .orElseGet(OptionalInt::empty);
    }
}
