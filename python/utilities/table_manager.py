#!/usr/bin/env python3
import logging
import sys
from typing import Any, Callable

import psycopg
from psycopg import Connection, Cursor

from utilities.citus import create_tables as create_tables_single_shard
from utilities.config import DbConfig
from utilities.connection_manager import connect_to_shards, close_shard_connections
from utilities.constants import EXIT_FAILURE, MAIN_DB_CONFIG
from utilities.queries import create_tables as create_tables_base, create_lookup_table


class TableManager:
    def __init__(self, logger_name: str = 'dbsetup.tables') -> None:
        self.logger = logging.getLogger(logger_name)

    def create_tables(self, params: DbConfig | tuple[DbConfig, ...], mode: str) -> None:
        self.logger.info(f"Attempting to create tables for mode: '{mode}'...")
        if mode == "single":
            assert isinstance(params, DbConfig)
            self._create_tables_single(params)
        elif mode == "single-shard":
            assert isinstance(params, DbConfig)
            self._create_tables_single_shard(params)
        elif mode == "sharded":
            assert isinstance(params, tuple)
            self._create_tables_sharded(params)
        elif mode == "sharded-lookup-table":
            assert isinstance(params, tuple)
            self._create_tables_lookup(params)
        else:
            self.logger.error(f"Invalid mode: {mode}")
            sys.exit(EXIT_FAILURE)

    def _create_tables_single(self, params: DbConfig) -> None:
        try:
            with psycopg.connect(str(params), autocommit=True) as conn:
                with conn.cursor() as cur:
                    create_tables_base(cur)
        except Exception as e:
            self.logger.error(f"Error creating tables for 'single' mode: {e}")
            sys.exit(EXIT_FAILURE)

    def _create_tables_single_shard(self, params: DbConfig) -> None:
        try:
            with psycopg.connect(str(params), autocommit=True) as conn:
                with conn.cursor() as cur:
                    create_tables_single_shard(cur)
        except Exception as e:
            self.logger.error(f"Error creating tables for 'single-shard' mode: {e}")
            sys.exit(EXIT_FAILURE)

    def _create_tables_sharded(self, params: tuple[DbConfig, ...]) -> None:
        for i, shard_info in enumerate(params):
            try:
                with psycopg.connect(str(shard_info), autocommit=True) as conn:
                    with conn.cursor() as cur:
                        create_tables_base(cur)
            except Exception as e:
                self.logger.error(f"Error creating tables for shard {i + 1} ('sharded' mode): {e}")
                sys.exit(EXIT_FAILURE)

    def _create_tables_lookup(self, params: tuple[DbConfig, ...]) -> None:
        try:
            with psycopg.connect(str(MAIN_DB_CONFIG), autocommit=True) as conn:
                with conn.cursor() as cur:
                    create_lookup_table(cur)
        except psycopg.OperationalError as e:
            self.logger.error(f"Error creating lookup table: {e}")
            sys.exit(EXIT_FAILURE)

        shard_connections = connect_to_shards(params, self.logger)
        try:
            self._execute_on_shards(shard_connections, create_tables_base, "table creation")
        finally:
            close_shard_connections(shard_connections, self.logger)

    def _execute_on_shards(
        self,
        connections: list[Connection],
        statement_executor: Callable[[Cursor[Any]], None],
        operation_name: str = "table operation",
    ) -> None:
        for i, conn in enumerate(connections):
            try:
                with conn.cursor() as cur:
                    statement_executor(cur)
                    self.logger.debug(f"Executed {operation_name} on Shard {i + 1}")
            except Exception as e:
                self.logger.error(f"Error executing {operation_name} on shard {i + 1}: {e}")
                sys.exit(EXIT_FAILURE)
