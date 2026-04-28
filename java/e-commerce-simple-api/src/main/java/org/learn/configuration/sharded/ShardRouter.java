package org.learn.configuration.sharded;

import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;

import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.UUID;

@Component
@Profile("sharded")
/*
 * This is essentially what Claude generated
 * when I asked it to generate the same logic as in the python script
 * python/utilities/commons/utilities.py(get_shard_index)
 * The idea is more important than the implementation itself.
 */
public class ShardRouter {

    private static final int NUM_SHARDS = 4;

    public int getShardIndex(UUID userId) {
        try {
            // Use raw UUID bytes (like Python's uuid.bytes)
            byte[] uuidBytes = new byte[16];
            long mostSigBits = userId.getMostSignificantBits();
            long leastSigBits = userId.getLeastSignificantBits();

            // Convert to byte array (big-endian, like Python)
            // Note from me: highlights a fundamental problem with the complexity associated
            // with sharding
            // You've got to essentially mimic the exact 1:1 logic as within the module
            // java doesn't really have a way to do that, so AI generated this.
            // Highlights another problem with systems that have this many moving parts
            // you've got to ensure all of them are consistent, and they may have subtle
            // differences.
            // The one liner in the python scripts becomes a somewhat complicated code piece
            for (int i = 0; i < 8; i++) {
                uuidBytes[i] = (byte) (mostSigBits >>> (8 * (7 - i)));
                uuidBytes[i + 8] = (byte) (leastSigBits >>> (8 * (7 - i)));
            }

            // SHA1 hash (like Python's hashlib.sha1)
            MessageDigest sha1 = MessageDigest.getInstance("SHA-1");
            byte[] hashDigest = sha1.digest(uuidBytes);

            // Take first 8 bytes and convert to int (like Python)
            long hashInt = 0;
            for (int i = 0; i < 8; i++) {
                hashInt = (hashInt << 8) | (hashDigest[i] & 0xFF);
            }

            // Use Math.floorMod to handle negative values correctly
            // (Java's % can return negative results for negative dividends)
            return Math.floorMod(hashInt, NUM_SHARDS);
        } catch (NoSuchAlgorithmException e) {
            throw new RuntimeException("SHA-1 algorithm not available", e);
        }
    }

    public int getShardIndex(String userId) {
        return getShardIndex(UUID.fromString(userId));
    }
}
