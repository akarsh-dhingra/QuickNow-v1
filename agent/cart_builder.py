"""Greedy knapsack cart builder with a hard budget constraint."""

from __future__ import annotations

import logging

import config
from models.cart import Cart, CartItem
from models.product import Product

logger = logging.getLogger("amazon_now.cart_builder")


class CartBudgetError(Exception):
    """Raised when a finished cart would exceed the budget (should not happen)."""


def build_cart_from_candidates(
    candidates: list[Product],
    budget: float,
    quantities: dict[str, int],
    user_id: str,
    justifications: dict[str, str],
    intent: str = "",
) -> Cart:
    """Assemble a budget-respecting cart from candidate products.

    Algorithm (greedy knapsack on value-per-rupee):
      1. effective_score = relevance_score / price for each candidate
      2. sort by effective_score descending
      3. greedily add items that fit the remaining budget, trying the desired
         quantity first then falling back to quantity 1
      4. enforce the hard budget constraint
    """
    budget = float(budget)
    quantities = quantities or {}
    justifications = justifications or {}

    cart = Cart(budget=budget, user_id=user_id, intent=intent)

    if budget <= 0:
        cart.add_note(
            "budget_too_low",
            "Please set a budget greater than ₹0 to build a cart.",
        )
        cart.recalculate_total()
        return cart

    if not candidates:
        cart.recalculate_total()
        return cart

    # 1. Score candidates by value-for-money. Guard against zero/negative price.
    def effective_score(p: Product) -> float:
        price = p.price if p.price > 0 else 1.0
        # Products with no relevance set still get a small baseline so they can
        # be picked when the agent forgot to score them.
        score = p.relevance_score if p.relevance_score > 0 else 1.0
        return score / price

    # 2. Sort descending by value-for-money, then cheaper first as a tiebreak.
    ranked = sorted(
        candidates,
        key=lambda p: (effective_score(p), -p.price),
        reverse=True,
    )

    remaining = budget
    items_added = 0
    out_of_stock: list[Product] = []
    out_of_budget: list[Product] = []
    in_stock_candidates = 0

    for product in ranked:
        if not product.in_stock:
            out_of_stock.append(product)
            continue

        in_stock_candidates += 1

        if items_added >= config.CART_MAX_ITEMS:
            # Cart is already at the item cap; remaining in-stock items are
            # left out for capacity reasons, not budget — don't flag them.
            continue

        desired_qty = int(quantities.get(product.product_id, 1) or 1)
        if desired_qty < 1:
            desired_qty = 1

        chosen_qty = 0
        # Try desired quantity, then degrade down to 1.
        for qty in range(desired_qty, 0, -1):
            if product.price * qty <= remaining + 1e-6:
                chosen_qty = qty
                break

        if chosen_qty == 0:
            # 3. Doesn't fit even at quantity 1 within the remaining budget.
            out_of_budget.append(product)
            continue

        justification = justifications.get(product.product_id, "").strip()
        if not justification:
            justification = (
                f"Good value pick for your needs at ₹{product.price:.0f} "
                f"per {product.unit}."
            )

        line_total = round(product.price * chosen_qty, 2)
        cart.items.append(
            CartItem(
                product=product,
                quantity=chosen_qty,
                justification=justification,
                line_total=line_total,
            )
        )
        remaining = round(remaining - line_total, 2)
        items_added += 1

    cart.recalculate_total()

    _record_skip_notes(
        cart,
        out_of_stock=out_of_stock,
        out_of_budget=out_of_budget,
        in_stock_candidates=in_stock_candidates,
        items_added=items_added,
        budget=budget,
    )

    # 6. Hard constraint: total must never exceed budget.
    if not cart.is_within_budget():
        raise CartBudgetError(
            f"Cart total ₹{cart.total:.2f} exceeds budget ₹{budget:.2f}"
        )

    return cart


# Show at most this many named items per note to avoid overwhelming the user.
_MAX_NAMED_IN_NOTE = 4


def _names(products: list[Product]) -> str:
    names = [p.name for p in products[:_MAX_NAMED_IN_NOTE]]
    extra = len(products) - len(names)
    joined = ", ".join(f"“{n}”" for n in names)
    if extra > 0:
        joined += f" and {extra} more"
    return joined


def _record_skip_notes(
    cart: Cart,
    out_of_stock: list[Product],
    out_of_budget: list[Product],
    in_stock_candidates: int,
    items_added: int,
    budget: float,
) -> None:
    """Attach clear, customer-facing notes about anything left out."""
    if out_of_stock:
        cart.add_note(
            "out_of_stock",
            f"Out of stock right now, so we left it out: {_names(out_of_stock)}.",
        )

    if out_of_budget:
        cheapest = min(out_of_budget, key=lambda p: p.price)
        cart.add_note(
            "out_of_budget",
            (
                f"Didn’t fit your ₹{budget:.0f} budget: {_names(out_of_budget)}. "
                f"The cheapest of these is “{cheapest.name}” at "
                f"₹{cheapest.price:.0f}."
            ),
        )

    # Nothing made it into the cart even though relevant in-stock items existed.
    if items_added == 0 and in_stock_candidates > 0:
        cart.add_note(
            "budget_too_low",
            (
                f"Your ₹{budget:.0f} budget is too low for these items — try "
                "increasing it to build a cart."
            ),
        )
