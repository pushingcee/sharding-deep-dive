from typing import Tuple

from psycopg import connect

from utilities.commons.db_config import DbConfig
from utilities.commons.utilities import get_optimal_thread_count
from utilities.constants import DEFAULT_BATCH_SIZE
from utilities.database.generators.base import DATA_GENERATOR
from utilities.database.generators.sharded_mode_generator import ShardedModeGenerator


class ShardedLookupTableGenerator(ShardedModeGenerator):
    """Data generator for sharded database mode with lookup table for routing."""

    def __init__(self, shard_configs: Tuple[DbConfig, ...], main_db_config: DbConfig, logger_name: str = "dbsetup.data_generator"):
        super().__init__(shard_configs, logger_name)
        self.main_db_config = main_db_config

    def generate_users(self, count: int, batch_size: int = DEFAULT_BATCH_SIZE) -> None:
        """Generate user records for 'sharded-lookup-table' mode with parallel processing."""
        self.logger.info(f"Generating {count} users ('sharded-lookup-table' mode) with parallel processing...")
        optimal_threads = get_optimal_thread_count(self.logger)
        total_generated = 0

        def process_user_batch_with_lookup(user_chunks: int) -> int:
            """Process a batch of users in a separate thread with thread-local connections."""
            batch_generated = 0
            shard_connections_local = {}  # Thread-local shard connection cache
            main_conn_local = None  # Thread-local main connection for lookup table

            try:
                # Create thread-local main connection for lookup table
                main_conn_local = connect(**self.main_db_config.to_dict(), autocommit=True)

                users = [DATA_GENERATOR.generate_user(sharded=True) for _ in range(user_chunks)]

                for user in users:
                    shard_index = user.target_shard_index

                    # Create shard connection if not exists in thread-local cache
                    if shard_index not in shard_connections_local:
                        shard_config = self.shard_configs[shard_index]
                        shard_connections_local[shard_index] = connect(**shard_config.to_dict(), autocommit=True)

                    # Insert user into shard
                    shard_conn = shard_connections_local[shard_index]
                    with shard_conn.cursor() as shard_cur:
                        shard_cur.execute(
                            """
                            INSERT INTO users (user_id, email, first_name, last_name, country, created_at, last_active, preferences)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                            """,
                            (
                                user.user_uuid,
                                user.email,
                                user.first_name,
                                user.last_name,
                                user.country,
                                user.created_at,
                                user.last_active,
                                user.preferences
                            )
                        )

                    # Insert lookup table entry
                    with main_conn_local.cursor() as lookup_cur:
                        lookup_cur.execute(
                            """
                            INSERT INTO user_data_shard (user_id, shard_id) VALUES (%s, %s)
                            """,
                            (user.user_uuid, user.target_shard_index + 1)
                        )

                    batch_generated += 1

                return batch_generated

            except Exception as e:
                self.logger.error(f"Error in sharded lookup user batch processing: {e}")
                return 0
            finally:
                # Clean up thread-local connections
                if main_conn_local:
                    try:
                        main_conn_local.close()
                    except Exception as e:
                        self.logger.error(f"Error closing thread-local main connection: {e}")

                for conn in shard_connections_local.values():
                    try:
                        conn.close()
                    except Exception as e:
                        self.logger.error(f"Error closing thread-local shard connection: {e}")

        # Process users in parallel batches
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
