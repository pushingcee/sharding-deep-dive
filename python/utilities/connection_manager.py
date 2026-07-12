import logging
from contextlib import contextmanager
from logging import Logger
from typing import Any, Iterator

from psycopg import Connection, connect
from psycopg_pool import ConnectionPool

from utilities.config import DbConfig


def connect_to_shards(shard_configs: tuple[DbConfig, ...], logger: Logger) -> list[Connection]:
    """Open a connection to each shard.

    On any failure, closes the already-opened connections and re-raises —
    callers (ultimately db_setup.main) decide how to exit. Library code
    never calls sys.exit.
    """
    shard_connections: list[Connection] = []
    for i, shard_info in enumerate(shard_configs):
        try:
            conn = connect(shard_info.conninfo, autocommit=True)
        except Exception:
            logger.error(f"Error connecting to Shard {i + 1} at {shard_info}")
            close_shard_connections(shard_connections, logger)
            raise
        shard_connections.append(conn)
        logger.info(f"Connected to Shard {i + 1} at {shard_info}")
    return shard_connections


def close_shard_connections(connections: list[Connection], logger: Logger) -> None:
    """Close all shard connections. Best-effort: a close failure is logged,
    never fatal — aborting a run because cleanup hiccupped helps nobody."""
    for i, conn in enumerate(connections):
        try:
            conn.close()
        except Exception as e:
            logger.error(f"Error closing connection to Shard {i + 1}: {e}")


class DatabaseManager:
    def __init__(
        self,
        db_config: DbConfig | None = None,
        logger_name: str = 'db.manager',
        max_size: int = 10,
        open: bool = True,
    ) -> None:
        self.logger = logging.getLogger(logger_name)
        if db_config is None:
            db_config = DbConfig()
        self.connection_pool = ConnectionPool(db_config.conninfo, max_size=max_size, open=open)

    def execute_query(self, query: str, params: tuple[Any, ...] | list[Any]) -> None:
        with self.connection_pool.connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, params)

    def execute_query_fetch_one(self, query: str, params: tuple[Any, ...] | list[Any]) -> tuple[Any, ...] | None:
        with self.connection_pool.connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, params)
                row: tuple[Any, ...] | None = cursor.fetchone()
                return row

    def execute_query_fetch_all(self, query: str, params: tuple[Any, ...] | list[Any]) -> list[tuple[Any, ...]]:
        with self.connection_pool.connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, params)
                rows: list[tuple[Any, ...]] = cursor.fetchall()
                return rows

    def execute_batch(self, query: str, params: list[tuple[Any, ...]]) -> None:
        with self.connection_pool.connection() as connection:
            with connection.cursor() as cursor:
                cursor.executemany(query, params)

    @contextmanager
    def get_connection(self) -> Iterator[Connection]:
        with self.connection_pool.connection() as conn:
            yield conn
