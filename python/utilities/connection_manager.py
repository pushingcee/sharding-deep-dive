#!/usr/bin/env python3
import logging
import sys
from contextlib import contextmanager
from logging import Logger
from typing import Any, Iterator

from psycopg import Connection, connect
from psycopg_pool import ConnectionPool

from utilities.config import DbConfig
from utilities.constants import EXIT_FAILURE


def connect_to_shards(shard_configs: tuple[DbConfig, ...], logger: Logger) -> list[Connection]:
    """Open a connection to each shard. On any failure, closes already-opened connections and exits."""
    shard_connections: list[Connection] = []
    for i, shard_info in enumerate(shard_configs):
        try:
            conn = connect(str(shard_info), autocommit=True)
            shard_connections.append(conn)
            logger.info(f"Connected to Shard {i + 1} at {shard_info['host']}:{shard_info['port']}")
        except Exception as e:
            logger.error(f"Error connecting to database Shard {i + 1}: {e}")
            for c in shard_connections:
                c.close()
            sys.exit(EXIT_FAILURE)
    return shard_connections


def close_shard_connections(connections: list[Connection], logger: Logger) -> None:
    """Close all shard connections."""
    for i, conn in enumerate(connections):
        try:
            conn.close()
            logger.info(f"Closed connection to Shard {i + 1}.")
        except Exception as e:
            logger.error(f"Error closing connection to Shard {i + 1}: {e}")
            sys.exit(EXIT_FAILURE)


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
        self.connection_pool = ConnectionPool(str(db_config), max_size=max_size, open=open)

    def execute_query(self, query: str, params: tuple[Any, ...] | list[Any]) -> None:
        with self.connection_pool.connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, params)

    def execute_query_fetch_one(self, query: str, params: tuple[Any, ...] | list[Any]) -> tuple[Any, ...] | None:
        with self.connection_pool.connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, params)
                return cursor.fetchone()

    def execute_query_fetch_all(self, query: str, params: tuple[Any, ...] | list[Any]) -> list[tuple[Any, ...]]:
        with self.connection_pool.connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, params)
                return cursor.fetchall()

    def execute_batch(self, query: str, params: list[tuple[Any, ...]]) -> None:
        with self.connection_pool.connection() as connection:
            with connection.cursor() as cursor:
                cursor.executemany(query, params)

    @contextmanager
    def get_connection(self) -> Iterator[Connection]:
        with self.connection_pool.connection() as conn:
            yield conn
