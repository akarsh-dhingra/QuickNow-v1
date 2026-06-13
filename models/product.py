"""Product domain model and DynamoDB (de)serialisation helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any


@dataclass
class Product:
    """A single catalog product.

    DynamoDB has no native float type, so prices are stored as ``Decimal`` on
    the wire and converted to/from ``float`` here.
    """

    product_id: str
    name: str
    category: str
    price: float
    tags: list[str]
    in_stock: bool
    unit: str
    relevance_score: float = 0.0

    def to_dynamo_item(self) -> dict[str, Any]:
        """Serialise to a dict suitable for ``Table.put_item``."""
        return {
            "product_id": self.product_id,
            "name": self.name,
            "category": self.category,
            # DynamoDB rejects float; store as Decimal.
            "price": Decimal(str(self.price)),
            "tags": list(self.tags),
            "in_stock": bool(self.in_stock),
            "unit": self.unit,
            "relevance_score": Decimal(str(self.relevance_score)),
        }

    @classmethod
    def from_dynamo_item(cls, item: dict[str, Any]) -> "Product":
        """Build a ``Product`` from a raw DynamoDB item dict."""
        return cls(
            product_id=str(item.get("product_id", "")),
            name=str(item.get("name", "")),
            category=str(item.get("category", "")),
            price=float(item.get("price", 0) or 0),
            tags=list(item.get("tags", []) or []),
            in_stock=bool(item.get("in_stock", True)),
            unit=str(item.get("unit", "")),
            relevance_score=float(item.get("relevance_score", 0) or 0),
        )

    def to_dict(self) -> dict[str, Any]:
        """Plain JSON-serialisable dict (floats, not Decimals)."""
        return {
            "product_id": self.product_id,
            "name": self.name,
            "category": self.category,
            "price": float(self.price),
            "tags": list(self.tags),
            "in_stock": bool(self.in_stock),
            "unit": self.unit,
            "relevance_score": float(self.relevance_score),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Product":
        return cls(
            product_id=str(d.get("product_id", "")),
            name=str(d.get("name", "")),
            category=str(d.get("category", "")),
            price=float(d.get("price", 0) or 0),
            tags=list(d.get("tags", []) or []),
            in_stock=bool(d.get("in_stock", True)),
            unit=str(d.get("unit", "")),
            relevance_score=float(d.get("relevance_score", 0) or 0),
        )
