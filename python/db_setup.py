#!/usr/bin/env python3
import argparse
import logging
import sys
from argparse import Namespace

from psycopg import Error

from utilities.config import DbConfig
from utilities.constants import (
    DEFAULT_USERS_COUNT,
    DEFAULT_PRODUCTS_COUNT,
    DEFAULT_ORDERS_PER_USER,
    DEFAULT_ITEMS_PER_ORDER,
    SHARD_CONFIGS,
    MAIN_DB_CONFIG,
    EXIT_FAILURE,
)
from utilities.generators import SingleGenerator, ShardedGenerator, ShardedLookupGenerator
from utilities.table_manager import TableManager

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger('dbsetup')

DEFAULT_CONFIG: DbConfig = DbConfig()


def generate_data(args: Namespace) -> None:
    logger.info(f"Starting data generation for mode: '{args.mode}'...")
    logger.info(
        f"Target counts: Users={args.users}, Products={args.products}, "
        f"Orders/User={args.orders_per_user}, Items/Order={args.items_per_order}"
    )

    try:
        if args.mode == "single" or args.mode == "single-shard":
            logger.info(f"Connecting to single database on {DEFAULT_CONFIG.host}:{DEFAULT_CONFIG.port}")
            with SingleGenerator(db_config=DEFAULT_CONFIG) as gen:
                gen.generate_users(args.users)
                gen.generate_products(args.products)
                gen.generate_orders(args.orders_per_user, args.items_per_order)
        elif args.mode == "sharded":
            logger.info("Using ShardedGenerator for sharded database mode")
            with ShardedGenerator(shard_configs=SHARD_CONFIGS) as gen:
                gen.generate_users(args.users)
                gen.generate_products(args.products)
                gen.generate_orders(args.orders_per_user, args.items_per_order)
        elif args.mode == "sharded-lookup-table":
            logger.info("Using ShardedLookupGenerator for sharded database mode with lookup table")
            with ShardedLookupGenerator(shard_configs=SHARD_CONFIGS, main_db_config=MAIN_DB_CONFIG) as gen:
                gen.generate_users(args.users)
                gen.generate_products(args.products)
                gen.generate_orders(args.orders_per_user, args.items_per_order)

    except Error as error:
        logger.error(f"Database connection failed during data generation: {error}")
        logger.error("Please check database connection parameters and ensure the server is running.")
        sys.exit(EXIT_FAILURE)
    except Exception as e:
        logger.error(f"An unexpected error occurred during data generation: {e}")
        sys.exit(EXIT_FAILURE)


def get_connection_params(args: Namespace) -> DbConfig | tuple[DbConfig, ...]:
    if args.mode == "sharded" or args.mode == "sharded-lookup-table":
        return SHARD_CONFIGS
    return DbConfig()


def main() -> None:
    parser = argparse.ArgumentParser(description='Database Setup and Mock Data Generation CLI Tool')

    parser.add_argument('--host', default=None, help=f"Database host (default: {DEFAULT_CONFIG.host})")

    parser.add_argument('--users', type=int, default=DEFAULT_USERS_COUNT, help='Number of users to generate')
    parser.add_argument('--products', type=int, default=DEFAULT_PRODUCTS_COUNT, help='Number of products to generate')
    parser.add_argument('--orders-per-user', type=int, default=DEFAULT_ORDERS_PER_USER, help='Average orders per user')
    parser.add_argument('--items-per-order', type=int, default=DEFAULT_ITEMS_PER_ORDER, help='Average items per order')

    parser.add_argument(
        '--mode',
        default="single",
        choices=['single', 'sharded', 'single-shard', 'sharded-lookup-table'],
        help='Database mode',
    )
    parser.add_argument('--skip-creation', action='store_true', help='Skip database and table creation steps')
    parser.add_argument('--skip-generation', action='store_true', help='Skip data generation step')
    parser.add_argument(
        '--log-level',
        default="INFO",
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        help='Set logging level',
    )
    args = parser.parse_args()

    log_level: int = getattr(logging, args.log_level.upper(), logging.INFO)
    logging.getLogger().setLevel(log_level)
    logger.setLevel(log_level)
    logger.info(f"Logging level set to: {args.log_level}")

    params = get_connection_params(args)
    table_manager = TableManager()

    if not args.skip_creation:
        logger.info("Running Database and Table Creation Steps...")
        table_manager.create_tables(params, args.mode)
        logger.info("Database and Table Creation Steps completed.")
    else:
        logger.info("Skipping Database and Table Creation as requested by --skip-creation.")

    if not args.skip_generation:
        logger.info("Running Data Generation Step...")
        generate_data(args)
    else:
        logger.info("Skipping Data Generation as requested by --skip-generation.")

    logger.info("Script execution finished.")


if __name__ == "__main__":
    main()
