#!/usr/bin/env python3
from contextlib import contextmanager
from logging import Logger
from typing import Any, Iterator

from psycopg import Connection
from psycopg_pool import ConnectionPool

from utilities.commons.db_config import DbConfig


class DatabaseManager:
    def __init__(self, db_config: DbConfig | None = None, logger_name: str = 'db.manager', max_size: int = 10, open: bool = True) -> None:
        self.logger = Logger(name= logger_name)
        if db_config is None:
            db_config = DbConfig()
        self.connection_pool = ConnectionPool(str(db_config), max_size=max_size, open=open)

    def execute_query(self, query: str, params: tuple[Any, ...] | list[Any]) -> None:
        """Execute a query without returning results (INSERT, UPDATE, DELETE without RETURNING)."""
        with self.connection_pool.connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    query,
                    params
                )

    def execute_query_fetch_one(self, query: str, params: tuple[Any, ...] | list[Any]) -> tuple[Any, ...] | None:
        """Execute a query and return a single row (INSERT...RETURNING, SELECT with LIMIT 1)."""
        with self.connection_pool.connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, params)
                return cursor.fetchone()

    def execute_query_fetch_all(self, query: str, params: tuple[Any, ...] | list[Any]) -> list[tuple[Any, ...]]:
        """Execute a query and return all rows (SELECT queries)."""
        with self.connection_pool.connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, params)
                return cursor.fetchall()

    def execute_batch(self, query: str, params: list[tuple[Any, ...]]) -> None:
        """Execute a batch of queries with different parameters (bulk INSERT)."""
        with self.connection_pool.connection() as connection:
            with connection.cursor() as cursor:
                cursor.executemany(
                    query,
                    params
                )

    @contextmanager
    def get_connection(self) -> Iterator[Connection]:
        """
        Get a connection from the pool for manual management.

        Use this for complex operations like:
        - Pagination with long-lived cursors
        - Multiple related queries with the same connection
        - Custom cursor operations

        Example:
            with db_manager.get_connection() as conn:
                with conn.cursor() as cur:
                    while True:
                        cur.execute("SELECT ... LIMIT %s OFFSET %s", ...)
                        batch = cur.fetchall()
                        if not batch:
                            break
                        # process batch
        """
        with self.connection_pool.connection() as conn:
            yield conn

