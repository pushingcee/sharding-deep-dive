from logging import Logger
from typing import Any, Callable, Tuple

from utilities.commons.data_generator import User
from utilities.constants import PRODUCT_LOG_INTERVAL, USER_LOG_INTERVAL


def generate_products_base(
    product_generator_func: Callable[[], Any],
    insert_func: Callable[[Any], None],
    count: int,
    logger: Logger,
    log_interval: int = PRODUCT_LOG_INTERVAL,
    mode_name: str = "unknown",
) -> int:
    """
    Base function for product generation that handles common logic.
    
    Args:
        logger: it's a logger man
        product_generator_func: Function that yields products (with or without UUIDs)
        insert_func: Function that handles the actual insertion
        count: Number of products to generate
        log_interval: How often to log progress
        mode_name: Name of the mode for logging
    
    Returns:
        Number of generated products
    """
    logger.info(f"Generating {count} products ('{mode_name}' mode)...")
    generated_count = 0
    
    for i in range(count):
        product = product_generator_func()
        try:
            insert_func(product)
            generated_count += 1
            if generated_count % log_interval == 0:
                logger.info(f"-> Generated {generated_count} products...")
        except Exception as e:
            logger.error(f"Error inserting product: {e}")

    logger.info(f"Finished generating products for '{mode_name}' mode. Total generated: {generated_count}")
    return generated_count

def generate_users_with_lookup_base(
    user_generator: Callable[[], User],
    insert_func: Callable[[User], None],
    lookup_insert_func: Callable[[User], None],
    count: int,
    logger: Logger,
    log_interval: int = USER_LOG_INTERVAL,
    mode_name: str = "unknown",
) -> Tuple[int, int]:

    logger.info(f"Generating {count} users with lookup table ('{mode_name}' mode)...")
    generated_count = 0
    skipped_count = 0
    
    for i in range(count):
        user = user_generator()
        try:
            lookup_insert_func(user)
            insert_func(user)
            generated_count += 1
            if generated_count % log_interval == 0:
                logger.info(f"-> Generated {generated_count} users with lookup entries...")
        except Exception as e:
            skipped_count += 1
            logger.warning(f"Skipping user due to error: {e} (Data: {user.email})")

    logger.info(
        f"Finished generating users with lookup table for '{mode_name}' mode. Total generated: {generated_count}, Skipped: {skipped_count}")
    
    return generated_count, skipped_count