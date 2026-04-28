package org.learn.repository.lookup;

import java.util.UUID;

public record ShardLocation(UUID user_id, int shard_id){
}
