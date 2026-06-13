"""Catalog data access against the ``qm_catalog`` DynamoDB table.

Uses the boto3 DynamoDB *resource* (not the low-level client). All AWS calls
are wrapped in try/except for ``botocore.exceptions.ClientError`` and re-raised
as :class:`CatalogError`.
"""

from __future__ import annotations

import logging
from functools import lru_cache

import boto3
from boto3.dynamodb.conditions import Attr
from botocore.exceptions import ClientError

import config
from models.product import Product

logger = logging.getLogger("amazon_now.catalog")


class CatalogError(Exception):
    """Raised when a catalog DynamoDB operation fails."""


@lru_cache(maxsize=1)
def _table():
    """Return a cached DynamoDB Table resource for the catalog."""
    resource = boto3.resource("dynamodb", region_name=config.AWS_REGION)
    return resource.Table(config.CATALOG_TABLE)


def _scan_all(**scan_kwargs) -> list[dict]:
    """Run a paginated scan, transparently following LastEvaluatedKey."""
    items: list[dict] = []
    table = _table()
    response = table.scan(**scan_kwargs)
    items.extend(response.get("Items", []))
    while "LastEvaluatedKey" in response:
        scan_kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]
        response = table.scan(**scan_kwargs)
        items.extend(response.get("Items", []))
    return items


def search_by_tags(tags: list[str], max_results: int = 20) -> list[Product]:
    """Return in-stock products matching ANY of ``tags``.

    Results are sorted by the number of matching tags (descending) and capped
    at ``max_results``.
    """
    if not tags:
        return []

    normalized = [t.strip().lower() for t in tags if t and t.strip()]
    if not normalized:
        return []

    try:
        # OR across all tags: contains(tags, t1) OR contains(tags, t2) ...
        filter_expr = None
        for tag in normalized:
            cond = Attr("tags").contains(tag)
            filter_expr = cond if filter_expr is None else (filter_expr | cond)
        # Only in-stock items are useful for a cart.
        filter_expr = filter_expr & Attr("in_stock").eq(True)

        raw_items = _scan_all(FilterExpression=filter_expr)
    except ClientError as exc:
        logger.error("search_by_tags failed: %s", exc)
        raise CatalogError(f"search_by_tags failed: {exc}") from exc

    tag_set = set(normalized)

    def match_count(item: dict) -> int:
        item_tags = {str(t).lower() for t in item.get("tags", [])}
        return len(tag_set & item_tags)

    raw_items.sort(key=match_count, reverse=True)
    products = [Product.from_dynamo_item(it) for it in raw_items[:max_results]]
    return products


def get_by_ids(product_ids: list[str]) -> list[Product]:
    """Batch-get products by id, preserving the input ordering."""
    if not product_ids:
        return []

    # De-duplicate while preserving order for the request.
    unique_ids: list[str] = []
    seen: set[str] = set()
    for pid in product_ids:
        if pid not in seen:
            seen.add(pid)
            unique_ids.append(pid)

    resource = boto3.resource("dynamodb", region_name=config.AWS_REGION)
    by_id: dict[str, Product] = {}

    try:
        # batch_get_item is limited to 100 keys per request.
        for start in range(0, len(unique_ids), 100):
            chunk = unique_ids[start : start + 100]
            request = {
                config.CATALOG_TABLE: {
                    "Keys": [{"product_id": pid} for pid in chunk]
                }
            }
            response = resource.batch_get_item(RequestItems=request)
            for item in response.get("Responses", {}).get(
                config.CATALOG_TABLE, []
            ):
                product = Product.from_dynamo_item(item)
                by_id[product.product_id] = product

            # Retry any unprocessed keys.
            unprocessed = response.get("UnprocessedKeys", {})
            while unprocessed:
                response = resource.batch_get_item(RequestItems=unprocessed)
                for item in response.get("Responses", {}).get(
                    config.CATALOG_TABLE, []
                ):
                    product = Product.from_dynamo_item(item)
                    by_id[product.product_id] = product
                unprocessed = response.get("UnprocessedKeys", {})
    except ClientError as exc:
        logger.error("get_by_ids failed: %s", exc)
        raise CatalogError(f"get_by_ids failed: {exc}") from exc

    # Preserve the caller's original ordering.
    ordered: list[Product] = []
    for pid in product_ids:
        if pid in by_id:
            ordered.append(by_id[pid])
            # Avoid duplicates if the caller passed the same id twice.
            del by_id[pid]
    return ordered


def get_all_in_category(category: str) -> list[Product]:
    """Return all in-stock products in a given category."""
    try:
        filter_expr = Attr("category").eq(category) & Attr("in_stock").eq(True)
        raw_items = _scan_all(FilterExpression=filter_expr)
    except ClientError as exc:
        logger.error("get_all_in_category failed: %s", exc)
        raise CatalogError(f"get_all_in_category failed: {exc}") from exc
    return [Product.from_dynamo_item(it) for it in raw_items]


def get_all_categories() -> list[str]:
    """Return the unique set of category values in the catalog."""
    try:
        raw_items = _scan_all(ProjectionExpression="category")
    except ClientError as exc:
        logger.error("get_all_categories failed: %s", exc)
        raise CatalogError(f"get_all_categories failed: {exc}") from exc
    categories = {str(it.get("category", "")) for it in raw_items}
    categories.discard("")
    return sorted(categories)
