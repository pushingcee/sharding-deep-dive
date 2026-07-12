#!/usr/bin/env python3
import argparse
import logging
import sys
from argparse import Namespace

from psycopg import Error

from utilities.config import DbConfig
from utilities.constants import (
    DATA_DIR,
    DEFAULT_CSV_USERS_COUNT,
    DEFAULT_USERS_COUNT,
    DEFAULT_PRODUCTS_COUNT,
    DEFAULT_ORDERS_PER_USER,
    DEFAULT_ITEMS_PER_ORDER,
    SHARD_CONFIGS,
    MAIN_DB_CONFIG,
    EXIT_FAILURE,
)
from utilities.csv_generator import CsvGenerator
from utilities.csv_loader import CsvLoader
from utilities.generators import SingleGenerator, ShardedGenerator, ShardedLookupGenerator
from utilities.table_manager import TableManager

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger('dbsetup')

DEFAULT_CONFIG: DbConfig = DbConfig()


def generate_csv(args: Namespace) -> None:
    generator = CsvGenerator(DATA_DIR, seed=args.seed)
    if generator.data_exists():
        logger.info(f"CSV data already exists at '{DATA_DIR}'. Delete the directory to regenerate.")
        return
    generator.generate_all(
        users_count=args.users,
        products_count=args.products,
        orders_per_user=args.orders_per_user,
        items_per_order=args.items_per_order,
    )


def generate_data_from_csv(args: Namespace) -> None:
    loader = CsvLoader(DATA_DIR)
    generator = CsvGenerator(DATA_DIR)

    if not generator.data_exists():
        raise FileNotFoundError(f"CSV data not found at '{DATA_DIR}'. Run with --generate-csv first.")

    loader.load_indexes()

    if args.mode == "single" or args.mode == "single-shard":
        loader.load_single(DEFAULT_CONFIG, args.users)
    elif args.mode == "sharded":
        loader.load_sharded(SHARD_CONFIGS, args.users)
    elif args.mode == "sharded-lookup-table":
        loader.load_sharded_lookup(SHARD_CONFIGS, MAIN_DB_CONFIG, args.users)


def generate_data(args: Namespace) -> None:
    logger.info(f"Starting data generation for mode: '{args.mode}'...")
    logger.info(
        f"Target counts: Users={args.users}, Products={args.products}, "
        f"Orders/User={args.orders_per_user}, Items/Order={args.items_per_order}"
    )

    if args.mode == "single" or args.mode == "single-shard":
        logger.info(f"Connecting to single database at {DEFAULT_CONFIG}")
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


def get_connection_params(args: Namespace) -> DbConfig | tuple[DbConfig, ...]:
    if args.mode == "sharded" or args.mode == "sharded-lookup-table":
        return SHARD_CONFIGS
    return DEFAULT_CONFIG


def run(args: Namespace) -> None:
    """The whole pipeline. Raises on any failure — a partially seeded database
    invalidates every benchmark run on top of it, so there is no
    log-and-continue here."""
    # --generate-csv: generate dataset, then exit
    if args.generate_csv:
        generate_csv(args)
        return

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
        if args.use_csv_seed:
            generate_data_from_csv(args)
        else:
            generate_data(args)
    else:
        logger.info("Skipping Data Generation as requested by --skip-generation.")

    logger.info("Script execution finished.")


def main() -> None:
    parser = argparse.ArgumentParser(description='Database Setup and Mock Data Generation CLI Tool')

    parser.add_argument('--users', type=int, default=None,
                        help=f'Number of users (default: {DEFAULT_CSV_USERS_COUNT:,} for --generate-csv, '
                             f'{DEFAULT_USERS_COUNT:,} otherwise)')
    parser.add_argument('--products', type=int, default=DEFAULT_PRODUCTS_COUNT,
                        help='Number of products to generate')
    parser.add_argument('--orders-per-user', type=int, default=DEFAULT_ORDERS_PER_USER,
                        help='Average orders per user')
    parser.add_argument('--items-per-order', type=int, default=DEFAULT_ITEMS_PER_ORDER,
                        help='Average items per order')

    parser.add_argument(
        '--mode',
        default="single",
        choices=['single', 'sharded', 'single-shard', 'sharded-lookup-table'],
        help='Database mode',
    )

    parser.add_argument('--generate-csv', action='store_true',
                        help=f'Generate CSV dataset to {DATA_DIR} (default: {DEFAULT_CSV_USERS_COUNT:,} users). '
                             f'Skips if data already exists.')
    parser.add_argument('--use-csv-seed', action='store_true',
                        help='Seed the database from pre-generated CSV files instead of generating data directly.')
    parser.add_argument('--seed', type=int, default=None,
                        help='RNG seed for reproducible --generate-csv output (same seed → same CSVs). '
                             'Direct DB generation is multi-threaded, so it is not run-order deterministic '
                             'even with a seed.')

    parser.add_argument('--skip-creation', action='store_true',
                        help='Skip database and table creation steps')
    parser.add_argument('--skip-generation', action='store_true',
                        help='Skip data generation step')
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

    # Resolve --users default based on active mode
    if args.users is None:
        args.users = DEFAULT_CSV_USERS_COUNT if args.generate_csv else DEFAULT_USERS_COUNT

    try:
        run(args)
    except Error as error:
        logger.error(f"Database error: {error}")
        sys.exit(EXIT_FAILURE)
    except Exception as error:
        logger.error(f"Unexpected error: {error}")
        sys.exit(EXIT_FAILURE)


if __name__ == "__main__":
    main()
