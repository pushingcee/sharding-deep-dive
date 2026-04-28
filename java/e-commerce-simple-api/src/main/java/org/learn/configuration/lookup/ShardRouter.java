package org.learn.configuration.lookup;

import org.learn.repository.lookup.ShardRoutingRepository;
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;

import java.util.UUID;

@Component
@Profile("lookup")
public class ShardRouter {
    private final ShardRoutingRepository shardRoutingRepository;

    public ShardRouter(ShardRoutingRepository shardRoutingRepository) {
        this.shardRoutingRepository = shardRoutingRepository;
    }

    public int getShardIndex(UUID userId) {
        return shardRoutingRepository.findById(userId)
                .orElseThrow(() -> new IllegalArgumentException("User not found in shard routing table: " + userId))
                .shard_id();
    }

}
