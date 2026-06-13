"""Create and seed the DynamoDB tables for Amazon Now / QuickMind.

Run once before launching the app:

    python db/seed_catalog.py

Creates ``qm_catalog`` (50 products) and ``qm_memory`` (one demo user) if they
do not already exist. Idempotent: safe to re-run.
"""

from __future__ import annotations

import os
import sys
import time
from decimal import Decimal

import boto3
from botocore.exceptions import ClientError

# Allow running both as a module (python -m db.seed_catalog) and as a script
# (python db/seed_catalog.py) by ensuring the project root is importable.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config  # noqa: E402


# ---------------------------------------------------------------------------
# Product catalog definition (50 products)
# Each tuple: (name, category, price, tags, unit)
# ---------------------------------------------------------------------------
CATALOG: list[tuple[str, str, float, list[str], str]] = [
    # --- GROCERY (15) ------------------------------------------------------
    ("Aashirvaad Atta 5kg", "Grocery", 280, ["staple", "breakfast", "dinner", "bulk"], "5kg"),
    ("Amul Butter 500g", "Grocery", 280, ["dairy", "breakfast", "quick-cook"], "500g"),
    ("Amul Full Cream Milk 1L", "Grocery", 68, ["dairy", "breakfast", "daily"], "1L"),
    ("Farm Fresh Eggs (dozen)", "Grocery", 90, ["protein", "breakfast", "quick-cook", "daily"], "dozen"),
    ("Onions 1kg", "Grocery", 40, ["vegetable", "dinner", "cooking-base", "daily"], "1kg"),
    ("Tomatoes 500g", "Grocery", 30, ["vegetable", "dinner", "cooking-base", "daily"], "500g"),
    ("Potatoes 1kg", "Grocery", 35, ["vegetable", "dinner", "budget-friendly"], "1kg"),
    ("Paneer 200g", "Grocery", 85, ["protein", "vegetarian", "dinner", "quick-cook"], "200g"),
    ("Basmati Rice 1kg", "Grocery", 120, ["staple", "dinner", "lunch"], "1kg"),
    ("Toor Dal 500g", "Grocery", 75, ["protein", "vegetarian", "dinner", "healthy"], "500g"),
    ("Spinach 250g", "Grocery", 25, ["vegetable", "healthy", "quick-cook", "dinner"], "250g"),
    ("Capsicum 250g", "Grocery", 40, ["vegetable", "dinner", "pizza", "stir-fry"], "250g"),
    ("Garlic 100g", "Grocery", 30, ["cooking-base", "dinner", "spice"], "100g"),
    ("Ginger 100g", "Grocery", 25, ["cooking-base", "dinner", "spice"], "100g"),
    ("Green Chillies 100g", "Grocery", 20, ["spice", "cooking-base", "daily"], "100g"),

    # --- BEVERAGES (8) -----------------------------------------------------
    ("Coca-Cola 2L", "Beverages", 95, ["party", "birthday", "cold-drink", "celebration"], "2L"),
    ("Sprite 2L", "Beverages", 90, ["party", "birthday", "cold-drink"], "2L"),
    ("Tropicana Orange Juice 1L", "Beverages", 120, ["healthy", "breakfast", "fruit-juice"], "1L"),
    ("Red Bull 250ml", "Beverages", 125, ["energy", "study", "late-night"], "250ml"),
    ("Paperboat Aam Panna 200ml (pack of 5)", "Beverages", 150, ["party", "birthday", "kids", "snack"], "pack of 5"),
    ("Bisleri Water 5L", "Beverages", 60, ["daily", "essential", "household"], "5L"),
    ("Nescafe Classic 100g", "Beverages", 280, ["breakfast", "morning", "coffee"], "100g"),
    ("Tata Tea Premium 500g", "Beverages", 220, ["breakfast", "morning", "daily"], "500g"),

    # --- SNACKS (12) -------------------------------------------------------
    ("Lay's Classic Salted (pack of 5)", "Snacks", 125, ["party", "birthday", "snack", "kids"], "pack of 5"),
    ("Kurkure Masala Munch (pack of 5)", "Snacks", 100, ["party", "snack", "kids"], "pack of 5"),
    ("Oreo Chocolate Cream (family pack)", "Snacks", 120, ["birthday", "dessert", "kids", "party"], "family pack"),
    ("Britannia Good Day Butter (pack of 3)", "Snacks", 90, ["breakfast", "snack", "kids"], "pack of 3"),
    ("Haldiram's Aloo Bhujia 400g", "Snacks", 130, ["snack", "party", "diwali", "evening"], "400g"),
    ("Maggi 2-Minute Noodles (pack of 12)", "Snacks", 168, ["quick-cook", "late-night", "kids", "emergency"], "pack of 12"),
    ("Dark Fantasy Choco Fills (pack of 3)", "Snacks", 135, ["birthday", "dessert", "kids", "party"], "pack of 3"),
    ("Cornitos Nachos (pack of 2)", "Snacks", 140, ["party", "birthday", "snack"], "pack of 2"),
    ("Parle-G Biscuits 1kg", "Snacks", 80, ["breakfast", "snack", "kids", "daily"], "1kg"),
    ("Uncle Chipps Spicy Treat (pack of 5)", "Snacks", 110, ["party", "snack"], "pack of 5"),
    ("Kit Kat (pack of 4)", "Snacks", 120, ["birthday", "dessert", "snack", "kids"], "pack of 4"),
    ("Cadbury Dairy Milk 160g", "Snacks", 160, ["birthday", "celebration", "dessert", "gift"], "160g"),

    # --- HOUSEHOLD (8) -----------------------------------------------------
    ("Surf Excel Matic 1kg", "Household", 290, ["household", "cleaning", "laundry", "essential"], "1kg"),
    ("Vim Dishwash Gel 500ml", "Household", 95, ["household", "cleaning", "kitchen", "essential"], "500ml"),
    ("Lizol Floor Cleaner 500ml", "Household", 120, ["household", "cleaning", "essential"], "500ml"),
    ("Harpic Toilet Cleaner 500ml", "Household", 130, ["household", "cleaning", "essential"], "500ml"),
    ("Dettol Handwash 250ml", "Household", 85, ["household", "hygiene", "daily", "essential"], "250ml"),
    ("Tissue Paper (pack of 4 rolls)", "Household", 120, ["household", "daily", "essential"], "pack of 4 rolls"),
    ("Scotch-Brite Scrub Pad (pack of 3)", "Household", 65, ["household", "kitchen", "cleaning"], "pack of 3"),
    ("Garbage Bags Medium (pack of 30)", "Household", 90, ["household", "daily", "essential"], "pack of 30"),

    # --- FRESH & READY (7) -------------------------------------------------
    ("Haldiram's Pav Bhaji Ready-to-Eat 300g", "Fresh & Ready", 110, ["dinner", "quick-cook", "no-cook", "emergency"], "300g"),
    ("MTR Dal Makhani Ready-to-Eat 300g", "Fresh & Ready", 120, ["dinner", "quick-cook", "no-cook", "emergency"], "300g"),
    ("McCain Smiles Frozen Snacks 415g", "Fresh & Ready", 175, ["party", "kids", "snack", "birthday", "quick-cook"], "415g"),
    ("Amul Cheese Slices (pack of 10)", "Fresh & Ready", 150, ["breakfast", "snack", "quick-cook", "sandwich"], "pack of 10"),
    ("Mother Dairy Curd 400g", "Fresh & Ready", 55, ["dairy", "daily", "healthy", "dinner"], "400g"),
    ("Puri Pav (pack of 8)", "Fresh & Ready", 35, ["breakfast", "quick-cook", "daily"], "pack of 8"),
    ("Bread (large loaf)", "Fresh & Ready", 45, ["breakfast", "daily", "sandwich", "quick-cook"], "large loaf"),
]


DEMO_USER = {
    "user_id": "demo_user",
    "preferences": ["vegetarian", "quick-cook"],
    "exclusions": [],
    "past_orders": [
        {
            "timestamp": "2026-06-01T19:30:00",
            "intent": "quick dinner for 2",
            "items": [
                "Paneer 200g",
                "Basmati Rice 1kg",
                "Toor Dal 500g",
                "Onions 1kg",
            ],
        },
        {
            "timestamp": "2026-06-05T08:00:00",
            "intent": "breakfast essentials",
            "items": [
                "Farm Fresh Eggs",
                "Bread",
                "Amul Butter 500g",
                "Tata Tea Premium 500g",
            ],
        },
    ],
}


def _slugify(name: str, index: int) -> str:
    """Deterministic product_id like ``p001-aashirvaad-atta-5kg``."""
    base = "".join(c.lower() if c.isalnum() else "-" for c in name)
    while "--" in base:
        base = base.replace("--", "-")
    base = base.strip("-")
    return f"p{index:03d}-{base}"


def _wait_until_active(table) -> None:
    table.meta.client.get_waiter("table_exists").wait(
        TableName=table.name
    )


def create_table_if_absent(resource, name: str, key_name: str):
    """Create a PAY_PER_REQUEST table keyed on ``key_name`` if absent."""
    client = resource.meta.client
    existing = client.list_tables().get("TableNames", [])
    if name in existing:
        print(f"Table '{name}' already exists — skipping create.")
        table = resource.Table(name)
        return table

    print(f"Creating table '{name}' ...")
    table = resource.create_table(
        TableName=name,
        KeySchema=[{"AttributeName": key_name, "KeyType": "HASH"}],
        AttributeDefinitions=[
            {"AttributeName": key_name, "AttributeType": "S"}
        ],
        BillingMode="PAY_PER_REQUEST",
    )
    _wait_until_active(table)
    print(f"Table '{name}' is ACTIVE.")
    return table


def seed_catalog(resource) -> int:
    table = create_table_if_absent(resource, config.CATALOG_TABLE, "product_id")
    count = 0
    with table.batch_writer() as batch:
        for idx, (name, category, price, tags, unit) in enumerate(CATALOG, 1):
            item = {
                "product_id": _slugify(name, idx),
                "name": name,
                "category": category,
                "price": Decimal(str(price)),
                "tags": tags,
                "in_stock": True,
                "unit": unit,
                "relevance_score": Decimal("0"),
            }
            batch.put_item(Item=item)
            count += 1
    return count


def seed_memory(resource) -> None:
    table = create_table_if_absent(resource, config.MEMORY_TABLE, "user_id")
    table.put_item(Item=DEMO_USER)
    print(f"Seeded demo user '{DEMO_USER['user_id']}' to {config.MEMORY_TABLE}")


def main() -> None:
    resource = boto3.resource("dynamodb", region_name=config.AWS_REGION)
    try:
        count = seed_catalog(resource)
        print(f"Seeded {count} products to {config.CATALOG_TABLE}")
        seed_memory(resource)
    except ClientError as exc:
        print(f"ERROR: DynamoDB operation failed: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
