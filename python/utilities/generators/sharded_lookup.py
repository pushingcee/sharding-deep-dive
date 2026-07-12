import uuid

from psycopg import connect

from utilities.config import DbConfig
from utilities.constants import DEFAULT_BATCH_SIZE
from utilities.generators.base import get_factory
from utilities.generators.sharded import ShardedGenerator, group_users_by_shard


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

        def process_user_batch_with_lookup(chunk_count: int) -> int:
            factory = get_factory()
            users = [factory.generate_user(sharded=True) for _ in range(chunk_count)]
            users_by_shard = group_users_by_shard(users)
            lookup_data: list[tuple[uuid.UUID, int]] = [
                (user.user_uuid, user.target_shard_index + 1)
                for user in users
                if user.target_shard_index is not None
            ]

            batch_generated = 0
            for shard_index, user_rows in users_by_shard.items():
                with connect(self.shard_configs[shard_index].conninfo) as conn:
                    with conn.cursor() as cur:
                        cur.executemany(self.INSERT_USERS_SQL, user_rows)
                    conn.commit()
                batch_generated += len(user_rows)

            # The lookup rows ARE the routing architecture: a user on a shard
            # without a lookup entry is permanently unreachable in lookup mode
            # and shows up as fake 404s in the benchmark. Any failure here
            # must abort the seed run, never be logged-and-ignored.
            with connect(self.main_db_config.conninfo) as main_conn:
                with main_conn.cursor() as cur:
                    cur.executemany(
                        "INSERT INTO user_data_shard (user_id, shard_id) VALUES (%s, %s)",
                        lookup_data,
                    )
                main_conn.commit()

            return batch_generated

        total = self.run_user_batches(count, batch_size, process_user_batch_with_lookup)
        self.logger.info(f"Finished generating users ('sharded-lookup-table' mode). Total generated: {total}")
