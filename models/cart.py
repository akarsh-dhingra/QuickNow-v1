"""Cart and CartItem domain models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .product import Product


@dataclass
class CartItem:
    """A line item in the cart."""

    product: Product
    quantity: int
    justification: str
    line_total: float = 0.0

    def __post_init__(self) -> None:
        # Keep line_total consistent if not explicitly provided.
        if not self.line_total:
            self.line_total = round(self.product.price * self.quantity, 2)

    def to_dict(self) -> dict[str, Any]:
        return {
            "product": self.product.to_dict(),
            "quantity": int(self.quantity),
            "justification": self.justification,
            "line_total": float(self.line_total),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "CartItem":
        return cls(
            product=Product.from_dict(d["product"]),
            quantity=int(d.get("quantity", 1)),
            justification=str(d.get("justification", "")),
            line_total=float(d.get("line_total", 0) or 0),
        )


@dataclass
class Cart:
    """A complete shopping cart with budget accounting."""

    items: list[CartItem] = field(default_factory=list)
    budget: float = 0.0
    total: float = 0.0
    remaining_budget: float = 0.0
    user_id: str = ""
    intent: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def add_item(self, item: CartItem) -> None:
        """Add a line item (or merge quantity if product already present)."""
        for existing in self.items:
            if existing.product.product_id == item.product.product_id:
                existing.quantity += item.quantity
                existing.line_total = round(
                    existing.product.price * existing.quantity, 2
                )
                self.recalculate_total()
                return
        self.items.append(item)
        self.recalculate_total()

    def remove_item(self, product_id: str) -> None:
        """Remove a line item by product_id and re-total."""
        self.items = [
            it for it in self.items if it.product.product_id != product_id
        ]
        self.recalculate_total()

    def recalculate_total(self) -> None:
        """Recompute line totals, cart total and remaining budget."""
        running = 0.0
        for it in self.items:
            it.line_total = round(it.product.price * it.quantity, 2)
            running += it.line_total
        self.total = round(running, 2)
        self.remaining_budget = round(self.budget - self.total, 2)

    def is_within_budget(self) -> bool:
        return self.total <= self.budget + 1e-6

    def to_dict(self) -> dict[str, Any]:
        return {
            "items": [it.to_dict() for it in self.items],
            "budget": float(self.budget),
            "total": float(self.total),
            "remaining_budget": float(self.remaining_budget),
            "user_id": self.user_id,
            "intent": self.intent,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Cart":
        cart = cls(
            items=[CartItem.from_dict(i) for i in d.get("items", [])],
            budget=float(d.get("budget", 0) or 0),
            total=float(d.get("total", 0) or 0),
            remaining_budget=float(d.get("remaining_budget", 0) or 0),
            user_id=str(d.get("user_id", "")),
            intent=str(d.get("intent", "")),
            timestamp=str(d.get("timestamp", datetime.now().isoformat())),
        )
        # Ensure derived fields are coherent even if persisted values drifted.
        cart.recalculate_total()
        return cart
