import hashlib
from logging import Logger
import os
from uuid import UUID

def get_optimal_thread_count(logger: Logger) -> int:
    cpu_count = os.cpu_count() or 1
    optimal_threads = max(1, int(cpu_count * 0.8))
    logger.info(f"Detected {cpu_count} CPU cores, using {optimal_threads} threads (80%)")
    return optimal_threads

def get_shard_index(key_uuid: UUID) -> int:
    uuid_bytes = key_uuid.bytes
    hash_object = hashlib.sha1(uuid_bytes)
    hash_digest = hash_object.digest()
    hash_int = int.from_bytes(hash_digest[:8], byteorder='big', signed=False)
    shard_index = hash_int % 4
    return shard_index