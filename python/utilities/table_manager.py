import logging
from typing import Any, Callable

import psycopg
from psycopg import Cursor

from utilities.citus import create_tables as create_tables_single_shard
from utilities.config import DbConfig
from utilities.constants import MAIN_DB_CONFIG
from utilities.queries import create_tables as create_tables_base, create_lookup_table


class TableManager:
    """Creates schemas per mode. Raises on failure — exit codes are
    db_setup.main's job, not library code's."""

    def __init__(self, logger_name: str = 'dbsetup.tables') -> None:
        self.logger = logging.getLogger(logger_name)

    def create_tables(self, params: DbConfig | tuple[DbConfig, ...], mode: str) -> None:
        self.logger.info(f"Creating tables for mode: '{mode}'...")
        if mode == "single":
            self._create_tables_on(self._require_single(params, mode), create_tables_base)
        elif mode == "single-shard":
            self._create_tables_on(self._require_single(params, mode), create_tables_single_shard)
        elif mode == "sharded":
            for config in self._require_shards(params, mode):
                self._create_tables_on(config, create_tables_base)
        elif mode == "sharded-lookup-table":
            self._create_tables_on(MAIN_DB_CONFIG, create_lookup_table)
            for config in self._require_shards(params, mode):
                self._create_tables_on(config, create_tables_base)
        else:
            raise ValueError(f"Invalid mode: {mode}")
        self.logger.info(f"Table creation complete for mode: '{mode}'.")

    def _create_tables_on(self, config: DbConfig, statement_executor: Callable[[Cursor[Any]], None]) -> None:
        with psycopg.connect(config.conninfo, autocommit=True) as conn:
            with conn.cursor() as cur:
                statement_executor(cur)
        self.logger.debug(f"Tables created on {config}")

    @staticmethod
    def _require_single(params: DbConfig | tuple[DbConfig, ...], mode: str) -> DbConfig:
        if not isinstance(params, DbConfig):
            raise TypeError(f"Mode '{mode}' requires a single DbConfig, got {type(params).__name__}")
        return params

    @staticmethod
    def _require_shards(params: DbConfig | tuple[DbConfig, ...], mode: str) -> tuple[DbConfig, ...]:
        if not isinstance(params, tuple):
            raise TypeError(f"Mode '{mode}' requires a tuple of shard DbConfigs, got {type(params).__name__}")
        return params
