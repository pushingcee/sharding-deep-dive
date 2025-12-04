#!/usr/bin/env python3
import argparse
import logging
import sys
import time
from argparse import Namespace

from psycopg import Cursor, Error

from utilities.commons.data_generator import DataGenerator
from utilities.constants import *
from utilities.database.generators import SingleModeGenerator, ShardedModeGenerator, ShardedLookupTableGenerator
from utilities.database.table_manager import TableManager
from utilities.generators.base_generator import generate_products_base

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('dbsetup')

DEFAULT_CONFIG: DbConfig = DbConfig()

SHARD_CONFIGS: Tuple[DbConfig, DbConfig, DbConfig, DbConfig] = (
    DbConfig(port=SHARD_PORTS[1]),
    DbConfig(port=SHARD_PORTS[2]),
    DbConfig(port=SHARD_PORTS[3]),
    DbConfig(port=SHARD_PORTS[4])
)

DATA_GENERATOR = DataGenerator()

def generate_products_single(cur: Cursor, count: int) -> None:
    """Generate product records for 'single' mode (DB generates UUID)."""

    def product_generator():
        return DATA_GENERATOR.generate_product()

    def insert_product(product):
        cur.execute("""
            INSERT INTO products (name, description, price, category, technical_specs)
            VALUES (%s, %s, %s, %s, %s)""",
                (
                product.name,
                product.description,
                product.price,
                product.category,
                product.technical_specs)
                )

    generate_products_base(product_generator, insert_product, count, logger, PRODUCT_LOG_INTERVAL, "single")

def generate_data(params, args: Namespace) -> None:
    """Generate mock data based on provided args and mode."""
    start_time = time.time()
    logger.info(f"Starting data generation for mode: '{args.mode}'...")
    logger.info(f"Target counts: Users={args.users}, Products={args.products}, Orders/User={args.orders_per_user}, Items/Order={args.items_per_order}")

    try:
        if args.mode == "single" or args.mode == "single-shard":
            logger.info(f"Connecting to single database: {params['dbname']} on {params['host']}:{params['port']}")
            data_generator = SingleModeGenerator(db_config=DEFAULT_CONFIG)
            data_generator.generate_users(args.users)
            data_generator.generate_products(args.products)
            data_generator.generate_orders(args.orders_per_user, args.items_per_order)
        elif args.mode == "sharded":
            logger.info("Using ShardedModeGenerator for sharded database mode")
            sharded_generator = ShardedModeGenerator(shard_configs=SHARD_CONFIGS)
            sharded_generator.generate_users(args.users)
            sharded_generator.generate_products(args.products)
            sharded_generator.generate_orders(args.orders_per_user, args.items_per_order)
        elif args.mode == "sharded-lookup-table":
            logger.info("Using ShardedLookupTableGenerator for sharded database mode with lookup table")
            main_db_config = DbConfig(port=SHARD_PORTS[0])
            lookup_generator = ShardedLookupTableGenerator(shard_configs=SHARD_CONFIGS, main_db_config=main_db_config)
            lookup_generator.generate_users(args.users)
            lookup_generator.generate_products(args.products)
            lookup_generator.generate_orders(args.orders_per_user, args.items_per_order)

    except Error as error:
        logger.error(f"Database connection failed during data generation: {error}")
        logger.error("Please check database connection parameters and ensure the server is running.")
        sys.exit(EXIT_FAILURE)
    except Exception as e:
        logger.error(f"An unexpected error occurred during data generation: {e}")
        sys.exit(EXIT_FAILURE)

    elapsed = time.time() - start_time
    logger.info(f"Data generation completed in {elapsed:.2f} seconds")

def get_connection_params(args: Namespace) -> DbConfig | tuple[DbConfig, DbConfig, DbConfig, DbConfig]:
    if args.mode == "sharded" or args.mode == "sharded-lookup-table":
        return SHARD_CONFIGS
    else:
        config = DbConfig()
        return config


def main():
    parser = argparse.ArgumentParser(description='Database Setup and Mock Data Generation CLI Tool')

    # TODO: implement later
    parser.add_argument('--host', default=None, help=f"Database host (default: {DEFAULT_CONFIG['host']})")
    # parser.add_argument('--port', default=None, type=int, help=f"Database port (default: {DEFAULT_CONFIG['port']})")
    # parser.add_argument('--user', default=None, help=f"Database user (default: {DEFAULT_CONFIG['user']})")
    # parser.add_argument('--password', default=None, help='Database password (default: empty)')
    # parser.add_argument('--dbname', default=None, help=f"Database name (default: {DEFAULT_CONFIG['dbname']})")

    parser.add_argument('--users', type=int, default=DEFAULT_USERS_COUNT, help='Number of users to generate')
    parser.add_argument('--products', type=int, default=DEFAULT_PRODUCTS_COUNT, help='Number of products to generate')
    parser.add_argument('--orders-per-user', type=int, default=DEFAULT_ORDERS_PER_USER, help='Average orders per user')
    parser.add_argument('--items-per-order', type=int, default=DEFAULT_ITEMS_PER_ORDER, help='Average items per order')

    parser.add_argument('--mode', default="single", choices=['single', 'sharded', 'single-shard', 'sharded-lookup-table'],
                        help='Database mode: "single" (single DB, SERIAL PKs), "sharded" (multiple DBs, UUID PKs, app sharding), "single-shard" (single DB, UUID PKs, DB default UUIDs, composite item key)')

    parser.add_argument('--skip-creation', action='store_true', help='Skip database and table creation steps')
    parser.add_argument('--skip-generation', action='store_true', help='Skip data generation step')
    parser.add_argument('--log-level', default="INFO", choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                        help='Set logging level')
    args = parser.parse_args()

    log_level: int = getattr(logging, args.log_level.upper(), logging.INFO)
    logging.getLogger().setLevel(log_level)
    logger.setLevel(log_level)
    logger.info(f"Logging level set to: {args.log_level}")
    table_manager = TableManager()
    params = get_connection_params(args)

    if not args.skip_creation:
        logger.info("Running Database and Table Creation Steps...")
        table_manager.create_tables(params, args.mode)
        logger.info("Database and Table Creation Steps completed.")
    else:
        logger.info("Skipping Database and Table Creation as requested by --skip-creation.")

    if not args.skip_generation:
        logger.info("Running Data Generation Step...")
        generate_data(params, args)
    else:
        logger.info("Skipping Data Generation as requested by --skip-generation.")

    logger.info("Script execution finished.")


if __name__ == "__main__":
    main()
