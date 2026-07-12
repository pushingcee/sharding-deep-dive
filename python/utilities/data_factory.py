import json
import random
import uuid
from datetime import date, datetime, timedelta
from typing import Any, NamedTuple

from faker import Faker

from utilities.constants import (
    MIN_ORDER_AMOUNT,
    MAX_ORDER_AMOUNT,
    ORDER_AMOUNT_DECIMAL_PLACES,
    ORDER_STATUSES,
)
from utilities.shard_utils import get_shard_index

CATEGORIES: list[str] = ['Electronics', 'Clothing', 'Books', 'Home', 'Outdoor', 'Toys', 'Grocery']


class User(NamedTuple):
    user_uuid: uuid.UUID
    email: str
    first_name: str
    last_name: str
    country: str
    created_at: datetime
    last_active: date | None
    preferences: str
    target_shard_index: int | None


class Product(NamedTuple):
    product_uuid: uuid.UUID
    name: str
    price: float
    category: str
    technical_specs: str
    description: str


class Order(NamedTuple):
    user_id: uuid.UUID
    order_date: datetime
    total_amount: float
    status: str


class DataFactory:
    """Fake-data factory.

    Instances are NOT thread-safe (Faker and random.Random both keep mutable
    state), so concurrent generators must use one instance per thread — see
    utilities.generators.base.get_factory(). Each instance owns its RNGs:
    pass ``seed`` for reproducible output (used by the single-threaded CSV
    generation path).
    """

    def __init__(self, seed: int | None = None) -> None:
        self.fake = Faker()
        if seed is not None:
            self.fake.seed_instance(seed)
        self.rng = random.Random(seed)

    def generate_orders_for_user(self, user_id: uuid.UUID, user_created_at: datetime) -> Order:
        order_date = self.fake.date_time_between(start_date=user_created_at, end_date="now", tzinfo=None)
        total_amount = round(self.rng.uniform(MIN_ORDER_AMOUNT, MAX_ORDER_AMOUNT), ORDER_AMOUNT_DECIMAL_PLACES)
        status = self.fake.random_element(ORDER_STATUSES)
        return Order(
            user_id=user_id,
            order_date=order_date,
            total_amount=total_amount,
            status=status,
        )

    def generate_preferences(self) -> str:
        base_prefs: dict[str, Any] = {
            "theme": self.fake.random_element(("dark", "light")),
            "notifications": {
                "email": self.fake.boolean(),
                "push": self.fake.boolean(chance_of_getting_true=25),
            },
        }

        variation = self.fake.random_int(1, 5)

        if variation == 1:
            base_prefs.update({
                "accessibility": {
                    "font_size": self.fake.random_element(("normal", "large", "xl")),
                    "high_contrast": self.fake.boolean(),
                }
            })
        elif variation == 2:
            base_prefs.update({
                "language": self.fake.language_code(),
                "timezone": self.fake.timezone(),
            })
        elif variation == 3:
            base_prefs.update({
                "contact_prefs": {
                    "method": self.fake.random_element(("email", "sms", "push")),
                    "hours": f"{self.fake.random_int(8, 10)}am-{self.fake.random_int(5, 8)}pm",
                }
            })
        elif variation == 4:
            is_premium = self.fake.boolean(chance_of_getting_true=15)
            base_prefs.update({
                "premium": {
                    "is_active": is_premium,
                    "expires_at": self.fake.date_between(
                        start_date=datetime.now() + timedelta(days=1),
                        end_date=datetime.now() + timedelta(days=730),
                    ).isoformat() if is_premium else None,
                    "tier": self.fake.random_element(("bronze", "silver", "gold")) if is_premium else None,
                }
            })
        elif variation == 5:
            base_prefs.update({
                "interests": self.fake.words(nb=self.fake.random_int(1, 5), unique=True),
                "social_media": {
                    platform: self.fake.user_name()
                    for platform in self.fake.random_elements(
                        elements=("twitter", "linkedin", "github"),
                        unique=True,
                        length=self.fake.random_int(0, 2),
                    )
                },
                "metadata": {
                    "profile_updated_at": self.fake.iso8601(),
                    "update_count": self.fake.random_int(0, 15),
                },
            })
        return json.dumps(base_prefs)

    def generate_product(self) -> Product:
        product_uuid = uuid.uuid4()
        name = self.fake.word().capitalize() + " " + self.fake.bs().split(' ')[-1]
        price = round(self.rng.uniform(5.0, 2500.0), 2)
        category = self.fake.random_element(CATEGORIES)
        technical_specs = self.generate_technical_specs(category)
        description = self.fake.paragraph(nb_sentences=3)
        return Product(
            product_uuid=product_uuid,
            name=name,
            price=price,
            category=category,
            technical_specs=technical_specs,
            description=description,
        )

    def generate_user(self, sharded: bool = False) -> User:
        user_uuid = uuid.uuid4()
        first_name = self.fake.first_name()
        last_name = self.fake.last_name()
        # Unique by construction: the UUID fragment guarantees no collision on
        # the users.email UNIQUE constraint across threads and batches, without
        # fake.unique's shared state (not thread-safe) or its exhaustion limit
        # on large seeds.
        local_part = "".join(
            ch for ch in f"{first_name}.{last_name}".lower() if ch.isalnum() or ch == "."
        )
        email = f"{local_part}.{user_uuid.hex[:8]}@{self.fake.free_email_domain()}"
        country = self.fake.country_code()
        created_at = self.fake.date_time_between(start_date='-20y', end_date='now', tzinfo=None)
        last_active = self.fake.date_between(start_date='-20y', end_date='+30d') if self.fake.boolean() else None
        target_shard_index = get_shard_index(user_uuid) if sharded else None
        preferences = self.generate_preferences()
        return User(
            user_uuid=user_uuid,
            email=email,
            first_name=first_name,
            last_name=last_name,
            country=country,
            created_at=created_at,
            last_active=last_active,
            preferences=preferences,
            target_shard_index=target_shard_index,
        )

    def generate_technical_specs(self, category: str) -> str:
        base_specs: dict[str, Any] = {
            "weight_kg": round(self.rng.uniform(0.1, 25.0), 2),
            "material": self.fake.random_element(
                ("Plastic", "Metal", "Wood", "Fabric", "Composite", "Ceramic", "Glass")
            ),
            "origin_country": self.fake.country_code(),
            "release_year": self.fake.year(),
            "category": category.lower(),
        }

        if category == 'Electronics':
            base_specs.update({
                "battery_life_hr": self.fake.random_int(2, 48) if self.fake.boolean() else None,
                "connectivity": sorted(self.fake.random_elements(
                    elements=("Bluetooth 5.2", "Wi-Fi 6", "USB-C", "NFC", "LTE", "HDMI"),
                    unique=True,
                    length=self.fake.random_int(1, 4),
                )),
                "screen_size_inch": round(
                    self.fake.random_element((4.7, 5.5, 6.1, 10.2, 13.3, 15.6, 27.0)), 1
                ) if self.fake.boolean(chance_of_getting_true=70) else None,
                "storage_gb": self.fake.random_element(
                    (64, 128, 256, 512, 1024)
                ) if self.fake.boolean(chance_of_getting_true=60) else None,
                "warranty_years": self.fake.random_int(1, 3),
            })
        elif category == 'Clothing':
            base_specs.update({
                "size": self.fake.random_element(("XS", "S", "M", "L", "XL", "XXL")),
                "color": self.fake.color_name(),
                "care_instructions": self.fake.sentence(nb_words=5),
                "gender": self.fake.random_element(("Men", "Women", "Unisex")),
            })
        elif category == 'Books':
            base_specs.update({
                "isbn": self.fake.isbn13(),
                "pages": self.fake.random_int(50, 1200),
                "language": self.fake.language_code(),
                "publisher": self.fake.company(),
                "format": self.fake.random_element(("Paperback", "Hardcover", "Ebook", "Audiobook")),
            })
        elif category == 'Home':
            base_specs.update({
                "dimensions_cm": {
                    "width": round(self.rng.uniform(10, 200), 1),
                    "height": round(self.rng.uniform(10, 200), 1),
                    "depth": round(self.rng.uniform(5, 100), 1),
                },
                "power_watts": self.fake.random_int(50, 2500) if self.fake.boolean(chance_of_getting_true=40) else None,
                "capacity_liters": round(self.rng.uniform(0.5, 50), 1) if self.fake.boolean(chance_of_getting_true=30) else None,
                "assembly_required": self.fake.boolean(chance_of_getting_true=20),
            })
        elif category == 'Outdoor':
            base_specs.update({
                "waterproof_rating": self.fake.random_element(
                    ("IPX4", "IPX7", "IP68", "Not Rated")
                ) if self.fake.boolean(chance_of_getting_true=60) else "Not Rated",
                "temperature_rating_c": self.fake.random_int(-20, 15) if self.fake.boolean(chance_of_getting_true=30) else None,
                "packed_dimensions_cm": {
                    "width": round(self.rng.uniform(5, 50), 1),
                    "height": round(self.rng.uniform(5, 80), 1),
                    "depth": round(self.rng.uniform(2, 30), 1),
                },
                "load_capacity_kg": self.fake.random_int(5, 150) if self.fake.boolean(chance_of_getting_true=40) else None,
            })

        possible_certs = ['CE', 'FCC', 'RoHS', 'UL Listed', 'Energy Star', 'Fair Trade', 'ISO 9001']
        base_specs["certifications"] = sorted(self.fake.random_elements(
            elements=possible_certs, unique=True, length=self.fake.random_int(0, 3)
        ))

        return json.dumps(base_specs)
