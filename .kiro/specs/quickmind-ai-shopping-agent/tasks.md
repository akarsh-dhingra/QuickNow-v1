# Implementation Plan

## Overview

Implementation plan for QuickMind AI Shopping Agent — a full-stack, intent-driven AI shopping agent using AWS Bedrock, DynamoDB, and Streamlit. The project is structured in layers: config → models → database → agent → frontend → documentation.

## Tasks

- [ ] 1. Configuration Module (config.py)
  - [ ] 1.1 Verify config.py reads AWS_REGION, CATALOG_TABLE, MEMORY_TABLE, BEDROCK_REGION, BEDROCK_MODEL_ID, BEDROCK_FAST_MODEL_ID from environment variables with defaults
  - [ ] 1.2 Verify config.py reads behaviour settings (DEFAULT_USER_ID, MAX_AGENT_ITERATIONS, CART_MAX_ITEMS, AGENT_TIMEOUT_SECONDS) from environment variables
  - [ ] 1.3 Verify config.py contains zero hardcoded AWS credentials
- [ ] 2. Domain Models (models/)
  - [ ] 2.1 Implement Product dataclass with product_id, name, category, price, tags, in_stock, unit, relevance_score fields
  - [ ] 2.2 Implement Product.to_dict() and Product.from_dict() for plain dict serialisation
  - [ ] 2.3 Implement Product.to_dynamo_item() (float→Decimal) and Product.from_dynamo_item() (Decimal→float) for DynamoDB serialisation
  - [ ] 2.4 Implement CartItem dataclass with product, quantity, justification, line_total; __post_init__ auto-calculates line_total
  - [ ] 2.5 Implement CartItem.to_dict() and CartItem.from_dict()
  - [ ] 2.6 Implement Cart dataclass with items, budget, total, remaining_budget, user_id, intent, timestamp
  - [ ] 2.7 Implement Cart.add_item() (merges quantity if product already present), Cart.remove_item(), Cart.recalculate_total()
  - [ ] 2.8 Implement Cart.is_within_budget() returning True when total <= budget + 1e-6
  - [ ] 2.9 Implement Cart.to_dict() and Cart.from_dict() (from_dict calls recalculate_total for coherence)
  - [ ] 2.10 Write property test: Product dict round-trip — for all valid Products, from_dict(to_dict(p)) produces identical field values [PBT]
  - [ ] 2.11 Write property test: Product DynamoDB round-trip — for all valid Products, from_dynamo_item(to_dynamo_item(p)) produces equivalent values within 1e-6 tolerance [PBT]
  - [ ] 2.12 Write property test: CartItem dict round-trip — for all valid CartItems, from_dict(to_dict(item)) produces identical values [PBT]
  - [ ] 2.13 Write property test: Cart dict round-trip — for all valid Carts, from_dict(to_dict(cart)) produces equivalent items, budget, total, remaining_budget [PBT]
- [ ] 3. Database Layer — Catalog (db/catalog.py)
  - [ ] 3.1 Implement _table() with lru_cache returning DynamoDB Table resource for qm_catalog
  - [ ] 3.2 Implement _scan_all() for paginated scans following LastEvaluatedKey
  - [ ] 3.3 Implement search_by_tags(tags, max_results) — OR filter across tags, in_stock filter, sort by match count descending, cap at max_results
  - [ ] 3.4 Implement get_by_ids(product_ids) — batch_get_item with retry for unprocessed keys, preserving input order
  - [ ] 3.5 Implement get_all_in_category(category) — filtered scan for in-stock products
  - [ ] 3.6 Wrap all DynamoDB operations in try/except ClientError, raising CatalogError
- [ ] 4. Database Layer — Memory (db/memory.py)
  - [ ] 4.1 Implement get_user_memory(user_id) returning preferences, exclusions, past_orders (empty defaults for missing users)
  - [ ] 4.2 Implement update_memory(user_id, cart) — append order, cap at MAX_PAST_ORDERS (10)
  - [ ] 4.3 Implement get_frequent_products(user_id, top_n) using Counter for frequency analysis
  - [ ] 4.4 Wrap all DynamoDB operations in try/except ClientError, raising MemoryError
- [ ] 5. Database Layer — Seed Script (db/seed_catalog.py)
  - [ ] 5.1 Create seed script with 50 realistic Indian quick-commerce products across 5 categories (Grocery, Beverages, Snacks, Household, Fresh & Ready)
  - [ ] 5.2 Each product includes product_id, name, category, price (INR), tags list, in_stock (True), and unit
  - [ ] 5.3 Script uses batch_write_item to populate qm_catalog table and seeds demo user to qm_memory
- [ ] 6. Intent Classifier (agent/intent_classifier.py)
  - [ ] 6.1 Define IntentMode enum with FRICTIONLESS, INTENT_BASED, PREDICTIVE values
  - [ ] 6.2 Implement classify_intent(user_intent) using Bedrock Converse with BEDROCK_FAST_MODEL_ID
  - [ ] 6.3 Implement fallback logic: return INTENT_BASED on any ClientError, KeyError, or IndexError
  - [ ] 6.4 Implement token scanning to tolerate extra text in model response
- [ ] 7. Cart Builder (agent/cart_builder.py)
  - [ ] 7.1 Implement effective_score function: relevance_score / price (guard against zero/negative price)
  - [ ] 7.2 Sort candidates descending by effective_score with lower-price tiebreak
  - [ ] 7.3 Implement greedy selection loop: for each product, try desired qty down to 1; skip if qty 1 doesn't fit
  - [ ] 7.4 Enforce CART_MAX_ITEMS limit (12) in the selection loop
  - [ ] 7.5 Skip out-of-stock products in the selection loop
  - [ ] 7.6 Assign justification: use provided string if non-empty, otherwise generate default with price and unit
  - [ ] 7.7 Call cart.recalculate_total() and raise CartBudgetError if total > budget (hard constraint)
  - [ ] 7.8 Write property test: budget invariant — for all product lists and budgets > 0, cart.total <= budget [PBT]
  - [ ] 7.9 Write property test: item count bound — for all inputs, len(cart.items) <= CART_MAX_ITEMS [PBT]
  - [ ] 7.10 Write property test: no out-of-stock — for all inputs, every cart item has in_stock == True [PBT]
  - [ ] 7.11 Write property test: non-empty justification — for all carts, every CartItem.justification has len > 0 [PBT]
  - [ ] 7.12 Write property test: greedy ordering — items in cart appear in non-increasing effective_score order [PBT]
- [ ] 8. Agent Tools (agent/tools.py)
  - [ ] 8.1 Define SEARCH_CATALOG_TOOL schema with tags (required), category (optional), max_results (optional)
  - [ ] 8.2 Define GET_USER_MEMORY_TOOL schema with user_id (required)
  - [ ] 8.3 Define BUILD_CART_TOOL schema with product_ids, quantities, justifications, relevance_scores, budget, user_id
  - [ ] 8.4 Implement get_tool_config() returning full toolConfig payload
  - [ ] 8.5 Implement _handle_search_catalog: call catalog.search_by_tags, apply category filter, return JSON
  - [ ] 8.6 Implement _handle_get_user_memory: call memory.get_user_memory + get_frequent_products, return JSON
  - [ ] 8.7 Implement _handle_build_cart: resolve product_ids via catalog.get_by_ids, apply relevance_scores, call build_cart_from_candidates, store in LAST_BUILT_CART
  - [ ] 8.8 Implement execute_tool dispatcher with try/except returning error JSON on any failure
- [ ] 9. Bedrock Agent Loop (agent/bedrock_agent.py)
  - [ ] 9.1 Define SYSTEM_PROMPT instructing the agent on rules (budget, memory-first, exclusions, diverse tags, build_cart last)
  - [ ] 9.2 Implement _build_initial_message for new cart (intent, budget, user_id, step instructions)
  - [ ] 9.3 Implement _build_initial_message for change loop (existing cart state, change request, preservation rules)
  - [ ] 9.4 Implement run_agent main loop: send message, check stop_reason, dispatch tool_use blocks
  - [ ] 9.5 Handle tool_use stop_reason: iterate content blocks, call execute_tool, validate JSON, append tool results
  - [ ] 9.6 Handle end_turn stop_reason: extract Cart from LAST_BUILT_CART, validate budget, return
  - [ ] 9.7 Raise AgentTimeoutError after MAX_AGENT_ITERATIONS (10) without end_turn
  - [ ] 9.8 Raise AgentError on Bedrock ClientError or missing cart at end_turn
- [ ] 10. Streamlit Frontend (app.py)
  - [ ] 10.1 Implement custom CSS with Amazon-style colors (orange #FF9900, dark #131921)
  - [ ] 10.2 Implement session state initialization (cart, loading, user_id, conversation_history, intent_text, budget, pending_build, error)
  - [ ] 10.3 Implement _get_cart() and _store_cart() for Cart ↔ session_state dict conversion
  - [ ] 10.4 Implement left column: intent text_area, budget slider (₹50–₹2000, step ₹50), "Build My Cart" button
  - [ ] 10.5 Implement example chips ("Dinner for 4, ₹500", "Birthday party, ₹1000", "Quick breakfast, ₹200") with pending_build trigger
  - [ ] 10.6 Implement _build_cart_action: call run_agent, store cart, handle errors
  - [ ] 10.7 Implement right column cart display: item cards with name, unit×qty, category pill, line_total, justification, remove button
  - [ ] 10.8 Implement budget progress bar and remaining budget display (green/red)
  - [ ] 10.9 Implement change request input + "Update Cart" button calling _update_cart_action
  - [ ] 10.10 Implement _update_cart_action: call run_agent with cart_state and change_request
  - [ ] 10.11 Implement Checkout button: call memory.update_memory, show confirmation with balloons
- [ ] 11. Requirements File and Documentation
  - [ ] 11.1 Create requirements.txt with streamlit, boto3, botocore dependencies
  - [ ] 11.2 Create README.md with setup instructions, architecture overview, demo scenarios, and run command

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 1, "tasks": ["1", "6"] },
    { "wave": 2, "tasks": ["2", "11"] },
    { "wave": 3, "tasks": ["3", "4", "7"] },
    { "wave": 4, "tasks": ["5", "8"] },
    { "wave": 5, "tasks": ["9"] },
    { "wave": 6, "tasks": ["10"] }
  ],
  "dependencies": {
    "2": ["1"],
    "3": ["2"],
    "4": ["2"],
    "5": ["3"],
    "7": ["2"],
    "8": ["3", "4", "7"],
    "9": ["6", "8"],
    "10": ["9"],
    "11": ["1"]
  }
}
```

## Notes

- Tasks 1-5 involve mostly verifying existing code and making minor adjustments since the codebase is already largely implemented
- PBT (property-based tests) in tasks 2.10-2.13 and 7.8-7.12 use the Hypothesis library
- The seed script (task 5) must be run once before the app can function
- All AWS interactions use boto3's default credential chain — no credentials in code
