"""Core agentic loop driving the AWS Bedrock Converse API with tool use."""

from __future__ import annotations

import json
import logging

import boto3
from botocore.exceptions import ClientError

import config
from agent import tools
from agent.cart_builder import CartBudgetError
from models.cart import Cart

logger = logging.getLogger("amazon_now.bedrock_agent")


class AgentError(Exception):
    """Raised when the Bedrock agent fails irrecoverably."""


class AgentTimeoutError(AgentError):
    """Raised when the agentic loop exceeds MAX_AGENT_ITERATIONS."""


SYSTEM_PROMPT = (
    "You are QuickMind, an expert AI shopping agent for quick-commerce in "
    "India.\n"
    "Your job is to build the perfect shopping cart for the customer based on "
    "their intent and budget.\n"
    "Rules:\n"
    "- ALWAYS respect the budget — never exceed it\n"
    "- ALWAYS call get_user_memory first to check preferences and past orders\n"
    "- Prioritise products the customer has bought before when relevant\n"
    "- Always honour exclusions from memory (e.g. if they exclude dairy, "
    "include no dairy)\n"
    "- Call search_catalog with diverse, relevant tags — cast a wide net then "
    "narrow down\n"
    "- When the customer names a SPECIFIC product (e.g. 'add paneer'), call "
    "search_catalog with include_out_of_stock=true so you can tell them if "
    "that exact item is sold out\n"
    "- Select 4-10 items for a typical cart; fewer for specific requests\n"
    "- Always end by calling build_cart to finalise the cart\n"
    "- When calling build_cart, provide a relevance_scores map (0-100) and a "
    "one-sentence justification for every product_id you include\n"
    "- The build_cart result includes a 'notes' list describing anything left "
    "out (out of stock, over budget, not found). ALWAYS read these notes and "
    "clearly tell the customer about them in your final reply — never let a "
    "requested item disappear silently\n"
    "- Be decisive — do not ask clarifying questions, make smart assumptions"
)


def _client():
    return boto3.client("bedrock-runtime", region_name=config.BEDROCK_REGION)


def _build_initial_message(
    user_intent: str,
    budget: float,
    user_id: str,
    cart_state: dict | None,
    change_request: str | None,
) -> str:
    if cart_state is None:
        return (
            f"User intent: {user_intent}\n"
            f"Budget: ₹{budget}\n"
            f"User ID: {user_id}\n\n"
            "Please build the best possible shopping cart for this customer.\n"
            "Steps you must follow:\n"
            "1. Call get_user_memory to understand their preferences and "
            "history\n"
            "2. Call search_catalog with relevant tags extracted from the "
            "intent\n"
            "3. Select the best products considering preferences, exclusions, "
            "and budget\n"
            "4. Call build_cart with your selected product_ids and the budget\n"
            "5. Return a brief confirmation message summarising the cart"
        )
    return (
        "The customer has an existing cart and wants to make a change.\n"
        f"Existing cart: {json.dumps(cart_state)}\n"
        f"Change request: {change_request}\n"
        f"Budget: ₹{budget}\n"
        f"User ID: {user_id}\n\n"
        "Please modify the cart to fulfil the change request.\n"
        "- Keep all items that are NOT affected by the change request\n"
        "- Only search for and replace items that need to change\n"
        "- Call build_cart with the final list of product_ids (kept + new)\n"
        "- Do NOT rebuild the entire cart from scratch"
    )


def run_agent(
    user_intent: str,
    budget: float,
    user_id: str,
    cart_state: dict | None = None,
    change_request: str | None = None,
) -> Cart:
    """Run the full agentic loop and return the finished :class:`Cart`."""
    client = _client()
    tool_config = tools.get_tool_config()
    budget = float(budget)

    # Reset the shared build_cart result holder for this run.
    tools.LAST_BUILT_CART["cart"] = None

    initial_text = _build_initial_message(
        user_intent, budget, user_id, cart_state, change_request
    )
    messages: list[dict] = [
        {"role": "user", "content": [{"text": initial_text}]}
    ]

    for iteration in range(config.MAX_AGENT_ITERATIONS):
        try:
            response = client.converse(
                modelId=config.BEDROCK_MODEL_ID,
                messages=messages,
                system=[{"text": SYSTEM_PROMPT}],
                toolConfig=tool_config,
                inferenceConfig={"maxTokens": 2048, "temperature": 0.2},
            )
        except ClientError as exc:
            logger.error("Bedrock converse failed: %s", exc)
            raise AgentError(f"Bedrock request failed: {exc}") from exc

        stop_reason = response.get("stopReason")
        output_message = response["output"]["message"]
        # Always append the assistant turn to the running history.
        messages.append(output_message)

        if stop_reason == "tool_use":
            tool_result_blocks = []
            for block in output_message.get("content", []):
                if "toolUse" not in block:
                    continue
                tool_use = block["toolUse"]
                tool_name = tool_use["name"]
                tool_use_id = tool_use["toolUseId"]
                tool_input = tool_use.get("input", {}) or {}

                logger.info("Tool call: %s -> %s", tool_name, tool_input)
                result_json = tools.execute_tool(
                    tool_name, tool_input, user_id, budget
                )

                # Validate JSON; if broken, hand the agent an error result.
                try:
                    json.loads(result_json)
                except (ValueError, TypeError):
                    logger.warning("Tool '%s' returned invalid JSON", tool_name)
                    result_json = json.dumps({"error": "invalid tool result"})

                tool_result_blocks.append(
                    {
                        "toolResult": {
                            "toolUseId": tool_use_id,
                            "content": [{"json": json.loads(result_json)}],
                        }
                    }
                )

            messages.append({"role": "user", "content": tool_result_blocks})
            continue

        if stop_reason in ("end_turn", "stop_sequence", "max_tokens"):
            cart = tools.LAST_BUILT_CART.get("cart")
            if cart is not None:
                cart.intent = user_intent or cart.intent
                if not cart.is_within_budget():
                    raise CartBudgetError(
                        f"Final cart ₹{cart.total:.2f} exceeds budget "
                        f"₹{budget:.2f}"
                    )
                return cart
            # Model ended without ever calling build_cart.
            raise AgentError(
                "Agent finished without producing a cart. Please retry with a "
                "clearer intent."
            )

        # Unexpected stop reason — treat as terminal error.
        raise AgentError(f"Unexpected stop reason: {stop_reason}")

    raise AgentTimeoutError(
        f"Agent exceeded {config.MAX_AGENT_ITERATIONS} iterations without "
        "finishing."
    )
