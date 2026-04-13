import uuid
from datetime import datetime

from psycopg import connect

from utilities.config import DbConfig
from utilities.constants import DEFAULT_BATCH_SIZE
from utilities.generators.base import DATA_GENERATOR
from utilities.generators.sharded import ShardedGenerator
from utilities.shard_utils import get_optimal_thread_count


class ShardedLookupGenerator(ShardedGenerator):
    """Data generator for sharded database mode with lookup table for routing."""

    def __init__(
        self,
        shard_configs: tuple[DbConfig, ...],
        main_db_config: DbConfig,
        logger_name: str = "dbsetup.data_generator",
    ) -> None:
        super().__init__(shard_configs, logger_name)
        self.main_db_config = main_db_config

    def generate_users(self, count: int, batch_size: int = DEFAULT_BATCH_SIZE) -> None:
        self.logger.info(f"Generating {count} users ('sharded-lookup-table' mode) with batch inserts...")
        optimal_threads = get_optimal_thread_count(self.logger)
        total_generated = 0

        def process_user_batch_with_lookup(user_chunks: int) -> int:
            batch_generated = 0
            try:
                users = [DATA_GENERATOR.generate_user(sharded=True) for _ in range(user_chunks)]

                users_by_shard: dict[int, list[tuple[uuid.UUID, str, str, str, str, datetime, object, str]]] = {}
                lookup_data: list[tuple[uuid.UUID, int]] = []

                for user in users:
                    shard_index = user.target_shard_index
                    assert shard_index is not None, "target_shard_index must be set in sharded mode"
                    if shard_index not in users_by_shard:
                        users_by_shard[shard_index] = []
                    users_by_shard[shard_index].append((
                        user.user_uuid,
                        user.email,
                        user.first_name,
                        user.last_name,
                        user.country,
                        user.created_at,
                        user.last_active,
                        user.preferences,
                    ))
                    lookup_data.append((user.user_uuid, shard_index + 1))

                for shard_index, user_data_list in users_by_shard.items():
                    shard_config = self.shard_configs[shard_index]
                    try:
                        with connect(str(shard_config), autocommit=False) as conn:
                            with conn.cursor() as cur:
                                cur.executemany(
                                    "INSERT INTO users "
                                    "(user_id, email, first_name, last_name, country, created_at, last_active, preferences) "
                                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                                    user_data_list,
                                )
                            conn.commit()
                            batch_generated += len(user_data_list)
                    except Exception as e:
                        self.logger.error(f"Error inserting users to shard {shard_index + 1}: {e}")

                try:
                    with connect(str(self.main_db_config), autocommit=False) as main_conn:
                        with main_conn.cursor() as cur:
                            cur.executemany(
                                "INSERT INTO user_data_shard (user_id, shard_id) VALUES (%s, %s)",
                                lookup_data,
                            )
                        main_conn.commit()
                except Exception as e:
                    self.logger.error(f"Error inserting lookup table entries: {e}")

                return batch_generated
            except Exception as e:
                self.logger.error(f"Error in sharded lookup user batch processing: {e}")
                return 0

        remaining = count
        while remaining > 0:
            current_batch_size = min(batch_size, remaining)
            chunk_size = current_batch_size // optimal_threads
            remainder = current_batch_size % optimal_threads
            if chunk_size == 0:
                chunk_size = current_batch_size
            chunks_to_process = [chunk_size] * optimal_threads
            chunks_to_process[0] += remainder
            total_generated += sum(self.thread_pool_executor.map(process_user_batch_with_lookup, chunks_to_process))
            remaining -= current_batch_size
            self.logger.info(f"-> Generated {total_generated}/{count} users...")

        self.logger.info(f"Finished generating users ('sharded-lookup-table' mode). Total generated: {total_generated}")
