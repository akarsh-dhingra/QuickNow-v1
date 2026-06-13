"""User-memory data access against the ``qm_memory`` DynamoDB table."""

from __future__ import annotations

import logging
from collections import Counter
from functools import lru_cache

import boto3
from botocore.exceptions import ClientError

import config
from models.cart import Cart

logger = logging.getLogger("amazon_now.memory")

MAX_PAST_ORDERS = 10


class MemoryError(Exception):
    """Raised when a memory DynamoDB operation fails."""


@lru_cache(maxsize=1)
def _table():
    resource = boto3.resource("dynamodb", region_name=config.AWS_REGION)
    return resource.Table(config.MEMORY_TABLE)


def get_user_memory(user_id: str) -> dict:
    """Fetch a user's memory record.

    Returns an empty-but-valid structure if the user does not exist.
    """
    default = {"preferences": [], "exclusions": [], "past_orders": []}
    try:
        response = _table().get_item(Key={"user_id": user_id})
    except ClientError as exc:
        logger.error("get_user_memory failed: %s", exc)
        raise MemoryError(f"get_user_memory failed: {exc}") from exc

    item = response.get("Item")
    if not item:
        return default

    return {
        "preferences": list(item.get("preferences", []) or []),
        "exclusions": list(item.get("exclusions", []) or []),
        "past_orders": list(item.get("past_orders", []) or []),
    }


def update_memory(user_id: str, cart: Cart) -> None:
    """Append the completed cart to the user's past_orders (cap at 10)."""
    new_order = {
        "timestamp": cart.timestamp,
        "intent": cart.intent,
        "items": [it.product.name for it in cart.items],
    }

    try:
        existing = get_user_memory(user_id)
        past_orders = existing.get("past_orders", [])
        past_orders.append(new_order)
        # Keep only the 10 most recent orders.
        if len(past_orders) > MAX_PAST_ORDERS:
            past_orders = past_orders[-MAX_PAST_ORDERS:]

        _table().update_item(
            Key={"user_id": user_id},
            UpdateExpression=(
                "SET past_orders = :po, "
                "preferences = if_not_exists(preferences, :emptyl), "
                "exclusions = if_not_exists(exclusions, :emptyl)"
            ),
            ExpressionAttributeValues={
                ":po": past_orders,
                ":emptyl": [],
            },
        )
    except ClientError as exc:
        logger.error("update_memory failed: %s", exc)
        raise MemoryError(f"update_memory failed: {exc}") from exc


def get_frequent_products(user_id: str, top_n: int = 5) -> list[str]:
    """Return the ``top_n`` most frequently ordered product names."""
    memory = get_user_memory(user_id)
    counter: Counter[str] = Counter()
    for order in memory.get("past_orders", []):
        for name in order.get("items", []):
            counter[str(name)] += 1
    return [name for name, _ in counter.most_common(top_n)]
