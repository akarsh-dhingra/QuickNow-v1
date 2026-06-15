"""Bedrock tool schemas (for the Converse API) and the tool dispatcher.

The schemas follow the Bedrock Converse ``toolConfig`` shape:
    {"toolSpec": {"name", "description", "inputSchema": {"json": {...}}}}
"""

from __future__ import annotations

import json
import logging

from db import catalog, memory
from agent.cart_builder import build_cart_from_candidates

logger = logging.getLogger("amazon_now.tools")


# ---------------------------------------------------------------------------
# Tool schemas
# ---------------------------------------------------------------------------
SEARCH_CATALOG_TOOL = {
    "toolSpec": {
        "name": "search_catalog",
        "description": (
            "Search the product catalog by tags and optional category. "
            "Returns matching products with names, prices, and tags."
        ),
        "inputSchema": {
            "json": {
                "type": "object",
                "properties": {
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Semantic tags derived from the user intent, "
                            "e.g. ['dinner', 'vegetarian', 'quick-cook']."
                        ),
                    },
                    "category": {
                        "type": "string",
                        "description": (
                            "Optional category filter. One of: Grocery, "
                            "Beverages, Snacks, Household, Fresh & Ready."
                        ),
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum products to return (default 15).",
                    },
                    "include_out_of_stock": {
                        "type": "boolean",
                        "description": (
                            "Set true when the customer names a specific "
                            "product, so out-of-stock matches are also "
                            "returned (each carries an 'in_stock' flag). Use "
                            "this to tell the customer when a requested item "
                            "is sold out."
                        ),
                    },
                },
                "required": ["tags"],
            }
        },
    }
}

GET_USER_MEMORY_TOOL = {
    "toolSpec": {
        "name": "get_user_memory",
        "description": (
            "Retrieve the user's purchase history, preferences, and "
            "exclusions to personalise the cart."
        ),
        "inputSchema": {
            "json": {
                "type": "object",
                "properties": {
                    "user_id": {
                        "type": "string",
                        "description": "The user whose memory to retrieve.",
                    }
                },
                "required": ["user_id"],
            }
        },
    }
}

BUILD_CART_TOOL = {
    "toolSpec": {
        "name": "build_cart",
        "description": (
            "Assemble a final cart from selected product IDs within the given "
            "budget. Applies greedy optimisation. Always call this last after "
            "selecting candidate products."
        ),
        "inputSchema": {
            "json": {
                "type": "object",
                "properties": {
                    "product_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "product_ids to include in the cart.",
                    },
                    "quantities": {
                        "type": "object",
                        "description": (
                            "Optional map of product_id to desired quantity. "
                            "Defaults to 1 for unlisted products."
                        ),
                        "additionalProperties": {"type": "integer"},
                    },
                    "justifications": {
                        "type": "object",
                        "description": (
                            "Map of product_id to a one-sentence reason for "
                            "choosing that product."
                        ),
                        "additionalProperties": {"type": "string"},
                    },
                    "relevance_scores": {
                        "type": "object",
                        "description": (
                            "Optional map of product_id to a relevance score "
                            "(0-100) used to rank items during optimisation."
                        ),
                        "additionalProperties": {"type": "number"},
                    },
                    "budget": {
                        "type": "number",
                        "description": "Maximum total in INR.",
                    },
                    "user_id": {
                        "type": "string",
                        "description": "The user this cart is for.",
                    },
                },
                "required": ["product_ids", "budget", "user_id"],
            }
        },
    }
}


def get_tool_config() -> dict:
    """Return the full ``toolConfig`` payload for the Converse API."""
    return {
        "tools": [
            SEARCH_CATALOG_TOOL,
            GET_USER_MEMORY_TOOL,
            BUILD_CART_TOOL,
        ]
    }


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------
# build_cart stores its result here so the agent loop can recover the final
# Cart object (the model only sees the JSON string).
LAST_BUILT_CART: dict = {"cart": None}


def _handle_search_catalog(tool_input: dict) -> str:
    tags = tool_input.get("tags", []) or []
    category = tool_input.get("category")
    max_results = int(tool_input.get("max_results", 15) or 15)
    include_out_of_stock = bool(tool_input.get("include_out_of_stock", False))

    products = catalog.search_by_tags(
        tags,
        max_results=max_results,
        include_out_of_stock=include_out_of_stock,
    )
    if category:
        products = [p for p in products if p.category == category]

    payload = [
        {
            "product_id": p.product_id,
            "name": p.name,
            "category": p.category,
            "price": p.price,
            "tags": p.tags,
            "unit": p.unit,
            "in_stock": p.in_stock,
        }
        for p in products
    ]
    return json.dumps({"products": payload, "count": len(payload)})


def _handle_get_user_memory(tool_input: dict, fallback_user_id: str) -> str:
    user_id = tool_input.get("user_id") or fallback_user_id
    mem = memory.get_user_memory(user_id)
    # Summarise past orders to keep the payload compact.
    summary = []
    for order in mem.get("past_orders", []):
        summary.append(
            {
                "intent": order.get("intent", ""),
                "items": order.get("items", []),
            }
        )
    frequent = memory.get_frequent_products(user_id, top_n=5)
    return json.dumps(
        {
            "preferences": mem.get("preferences", []),
            "exclusions": mem.get("exclusions", []),
            "past_orders": summary,
            "frequent_products": frequent,
        }
    )


def _handle_build_cart(
    tool_input: dict, fallback_user_id: str, fallback_budget: float
) -> str:
    product_ids = tool_input.get("product_ids", []) or []
    quantities = tool_input.get("quantities", {}) or {}
    justifications = tool_input.get("justifications", {}) or {}
    relevance_scores = tool_input.get("relevance_scores", {}) or {}
    budget = float(tool_input.get("budget", fallback_budget) or fallback_budget)
    user_id = tool_input.get("user_id") or fallback_user_id

    products = catalog.get_by_ids(product_ids)

    # Detect requested ids the catalog could not resolve, so the customer can
    # be told instead of the item silently vanishing.
    found_ids = {p.product_id for p in products}
    not_found = [pid for pid in product_ids if pid and pid not in found_ids]

    # Apply agent-provided relevance scores so the greedy ranker can order
    # items by value-for-money.
    for p in products:
        if p.product_id in relevance_scores:
            try:
                p.relevance_score = float(relevance_scores[p.product_id])
            except (TypeError, ValueError):
                p.relevance_score = 1.0
        else:
            p.relevance_score = 1.0

    # Normalise quantity values to ints.
    norm_quantities: dict[str, int] = {}
    for pid, qty in quantities.items():
        try:
            norm_quantities[pid] = int(qty)
        except (TypeError, ValueError):
            norm_quantities[pid] = 1

    cart = build_cart_from_candidates(
        candidates=products,
        budget=budget,
        quantities=norm_quantities,
        user_id=user_id,
        justifications=justifications,
    )

    if not_found:
        cart.add_note(
            "not_found",
            (
                "We couldn’t find these in our catalog: "
                + ", ".join(not_found[:5])
                + "."
            ),
        )

    LAST_BUILT_CART["cart"] = cart

    return json.dumps(
        {
            "items": [
                {
                    "product_id": it.product.product_id,
                    "name": it.product.name,
                    "price": it.product.price,
                    "quantity": it.quantity,
                    "line_total": it.line_total,
                    "unit": it.product.unit,
                    "category": it.product.category,
                    "justification": it.justification,
                }
                for it in cart.items
            ],
            "total": cart.total,
            "budget": cart.budget,
            "remaining_budget": cart.remaining_budget,
            "item_count": len(cart.items),
            "within_budget": cart.is_within_budget(),
            # Surface customer-facing notes so the agent can mention them too.
            "notes": cart.notes,
        }
    )


def execute_tool(
    tool_name: str,
    tool_input: dict,
    user_id: str,
    budget: float,
) -> str:
    """Route a tool-use request to the correct handler and return JSON."""
    try:
        if tool_name == "search_catalog":
            return _handle_search_catalog(tool_input)
        if tool_name == "get_user_memory":
            return _handle_get_user_memory(tool_input, user_id)
        if tool_name == "build_cart":
            return _handle_build_cart(tool_input, user_id, budget)
        return json.dumps({"error": f"Unknown tool: {tool_name}"})
    except Exception as exc:  # noqa: BLE001 - surface to the agent as JSON
        logger.exception("Tool '%s' failed", tool_name)
        return json.dumps({"error": str(exc)})
