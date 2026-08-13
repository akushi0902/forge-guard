"""Faker-based synthetic data generation for demo endpoints.

All generator functions accept an optional ``seed`` parameter for reproducible
test data.  Pass the same seed to get the same output every time.
"""

from __future__ import annotations

import random
import string
from decimal import Decimal
from typing import Optional

from faker import Faker

_SUPPORTED_CURRENCIES = [
    "USD", "EUR", "GBP", "JPY", "AUD", "CAD", "CHF", "CNY", "SEK", "NZD",
]

_MERCHANT_CATEGORIES = [
    "Restaurant",
    "Electronics Store",
    "Clothing Boutique",
    "Pharmacy",
    "Gas Station",
    "Grocery Market",
    "Hotel & Lodging",
    "Airlines",
    "Streaming Service",
    "Software & SaaS",
]


def make_faker(seed: Optional[int] = None) -> Faker:
    """Return a :class:`~faker.Faker` instance with an optional fixed seed."""
    fake = Faker()
    if seed is not None:
        Faker.seed(seed)
        random.seed(seed)
    return fake


def generate_merchant_name(
    fake: Optional[Faker] = None, seed: Optional[int] = None
) -> str:
    """Return a realistic synthetic merchant name."""
    if fake is None:
        fake = make_faker(seed)
    category = random.choice(_MERCHANT_CATEGORIES)
    return f"{fake.company()} {category}"


def generate_transaction_amount(seed: Optional[int] = None) -> Decimal:
    """Return a random amount in the range [0.01, 9999.99]."""
    if seed is not None:
        random.seed(seed)
    cents = random.randint(1, 999999)
    return Decimal(cents) / Decimal("100")


def generate_currency_code(seed: Optional[int] = None) -> str:
    """Return a random ISO 4217 currency code from the supported set."""
    if seed is not None:
        random.seed(seed)
    return random.choice(_SUPPORTED_CURRENCIES)


def generate_card_last_four(seed: Optional[int] = None) -> str:
    """Return a random 4-digit card suffix."""
    if seed is not None:
        random.seed(seed)
    return "".join(random.choices(string.digits, k=4))


def generate_authorization_code(seed: Optional[int] = None) -> str:
    """Return a random authorization code string (e.g. 'AUTH3X7KQ2PW')."""
    if seed is not None:
        random.seed(seed)
    chars = string.ascii_uppercase + string.digits
    return "AUTH" + "".join(random.choices(chars, k=8))
