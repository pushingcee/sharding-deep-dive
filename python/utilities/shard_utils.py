import hashlib
import os
from logging import Logger
from uuid import UUID

from utilities.constants import DEFAULT_NUM_SHARDS


def get_optimal_thread_count(logger: Logger) -> int:
    cpu_count = os.cpu_count() or 1
    optimal_threads = max(1, int(cpu_count * 0.8))
    logger.info(f"Detected {cpu_count} CPU cores, using {optimal_threads} threads (80%)")
    return optimal_threads


def get_shard_index(key_uuid: UUID, num_shards: int = DEFAULT_NUM_SHARDS) -> int:
    uuid_bytes = key_uuid.bytes
    hash_object = hashlib.sha1(uuid_bytes)  # noqa: S324 - not used for security
    hash_digest = hash_object.digest()
    hash_int = int.from_bytes(hash_digest[:8], byteorder='big', signed=False)
    return hash_int % num_shards
