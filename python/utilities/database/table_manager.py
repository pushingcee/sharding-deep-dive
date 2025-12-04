#!/usr/bin/env python3
import logging
import sys
from typing import Tuple, List, Callable

import psycopg
from psycopg import Connection, Cursor

from utilities.citus import create_tables as create_tables_single_shard
from utilities.commons.db_config import DbConfig
from utilities.commons.queries import create_tables as create_tables_base, create_lookup_table
from utilities.constants import EXIT_FAILURE


class TableManager:
    def __init__(self, logger_name: str = 'dbsetup.tables'):
        """Initialize TableManager with logger."""
        self.logger = logging.getLogger(logger_name)

    def create_tables(self,
                      params,
                      mode: str
                      ) -> None:
        """
        Create tables based on the specified mode.

        Args:
            params: Database configuration(s) - single DbConfig or tuple of DbConfigs
            mode: Database mode ('single', 'sharded', 'single-shard')

        Raises:
            SystemExit: If table creation fails
        """
        self.logger.info(f"Attempting to create tables for mode: '{mode}'...")

        if mode == "single":
            self._create_tables_single(params)
        elif mode == "single-shard":
            self._create_tables_single_shard(params)
        elif mode == "sharded":
            self._create_tables_sharded(params)
        elif mode == "sharded-lookup-table":
            self._create_tables_lookup(params)
        else:
            self.logger.error(f"Invalid mode: {mode}")
            sys.exit(EXIT_FAILURE)

    def _create_tables_single(self, params: DbConfig) -> None:
        """Create tables for single database mode."""
        try:
            with psycopg.connect(**params.to_dict(), autocommit=True) as conn:
                with conn.cursor() as cur:
                    create_tables_base(cur)
        except Exception as e:
            self.logger.error(f"Error creating tables for 'single' mode: {e}")
            sys.exit(EXIT_FAILURE)

    def _create_tables_single_shard(self, params: DbConfig) -> None:
        """Create tables for single-shard database mode."""
        try:
            with psycopg.connect(**params.to_dict(), autocommit=True) as conn:
                with conn.cursor() as cur:
                    create_tables_single_shard(cur)
        except Exception as e:
            self.logger.error(f"Error creating tables for 'single-shard' mode: {e}")
            sys.exit(EXIT_FAILURE)

    def _create_tables_sharded(self, params: Tuple[DbConfig, DbConfig, DbConfig, DbConfig]) -> None:
        """Create tables for sharded database mode."""
        for i, shard_info in enumerate(params):
            try:
                with psycopg.connect(**shard_info.to_dict(), autocommit=True) as conn:
                    with conn.cursor() as cur:
                        create_tables_base(cur)
            except Exception as e:
                self.logger.error(f"Error creating tables for shard {i + 1} ('sharded' mode): {e}")
                sys.exit(EXIT_FAILURE)

    def _create_tables_lookup(self, params: Tuple[DbConfig, DbConfig, DbConfig, DbConfig]) -> None:
        # TODO: the dbconfig and the parameters that this method is accepting they should be merged,
        #  this method needs 4/5 dbs depending if lookup table is part of each table or just the central one
        db_config = DbConfig()
        try:
            with psycopg.connect(**db_config.to_dict(), autocommit=True) as conn:
                with conn.cursor() as cur:
                    create_lookup_table(cur)
        except psycopg.OperationalError as e:
            self.logger.error(f"Error creating lookup table: {e}")
            sys.exit(EXIT_FAILURE)
        shard_connections = self._connect_to_shards(params)
        try:
            self._execute_statement_for_tables(shard_connections, create_tables_base, "table creation")
        finally:
            self._cleanup_connections(shard_connections)

    def _execute_statement_for_tables(self,
                                      connections: List[Connection],
                                      statement_executor: Callable[[Cursor], None],
                                      operation_name: str = "table operation"
                                      ) -> None:
        """
        Execute statements on multiple connections using a callable function.

        Args:
            connections: List of database connections
            statement_executor: Function that takes a cursor and executes the statement
            operation_name: Name of the operation for logging purposes
        """
        for i, conn in enumerate(connections):
            try:
                with conn.cursor() as cur:
                    statement_executor(cur)
                    self.logger.debug(f"Executed {operation_name} on Shard {i + 1}")
            except Exception as e:
                self.logger.error(f"Error executing {operation_name} on shard {i + 1}: {e}")
                sys.exit(EXIT_FAILURE)

    def _connect_to_shards(self, shard_configs: Tuple[DbConfig, ...]) -> List[Connection]:
        """Connect to all shards, return list of connections."""
        shard_connections: List[Connection] = []

        for i, shard_info in enumerate(shard_configs):
            try:
                conn = psycopg.connect(**shard_info.to_dict(), autocommit=True)
                shard_connections.append(conn)
                self.logger.info(f"Connected to Shard {i + 1} at {shard_info['host']}:{shard_info['port']}")
            except Exception as e:
                self.logger.error(f"Error connecting to database Shard {i + 1}: {e}")
                for c in shard_connections:
                    c.close()
                sys.exit(EXIT_FAILURE)

        return shard_connections

    def _cleanup_connections(self, connections: List[Connection]) -> None:
        """Close all connections in the list."""
        for i, conn in enumerate(connections):
            try:
                conn.close()
                self.logger.info(f"Closed connection to Shard {i + 1}.")
            except Exception as e:
                self.logger.error(f"Error closing connection to Shard {i + 1}: {e}")
                sys.exit(EXIT_FAILURE)
