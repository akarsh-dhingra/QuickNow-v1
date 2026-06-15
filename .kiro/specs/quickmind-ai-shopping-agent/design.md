# Design Document: QuickMind AI Shopping Agent

## Overview

QuickMind is an intent-driven AI shopping agent that translates natural-language shopping requests into budget-constrained, personalised shopping carts using AWS Bedrock's tool-use agentic loop, DynamoDB for catalog and memory, and a greedy knapsack algorithm for budget optimisation. The Streamlit frontend provides a one-click cart-building experience with conversational refinement.

## Architecture

```
┌────────────────────────────────────────────────────────────────────┐
│                        Streamlit UI (app.py)                        │
│  Intent Input │ Budget Slider │ Cart Panel │ Change Input │ Checkout │
└────────────────┬───────────────────────────────────────────────────┘
                 │
                 ▼
┌────────────────────────────────────────────────────────────────────┐
│              QuickMind Agent (agent/bedrock_agent.py)               │
│  System Prompt → Bedrock Converse API → Tool-Use Loop (max 10)     │
└────────┬──────────────┬────────────────────────────┬───────────────┘
         │              │                            │
         ▼              ▼                            ▼
┌──────────────┐ ┌──────────────┐ ┌─────────────────────────────────┐
│search_catalog│ │get_user_memory│ │       build_cart                │
│ (db/catalog) │ │ (db/memory)  │ │ (agent/cart_builder.py)         │
└──────┬───────┘ └──────┬───────┘ │ Greedy Knapsack Algorithm       │
       │                │         └─────────────────────────────────┘
       ▼                ▼
┌──────────────────────────────────────┐
│         Amazon DynamoDB              │
│  qm_catalog (50 products)           │
│  qm_memory  (user history)          │
└──────────────────────────────────────┘
```

## Components and Interfaces

### 1. Configuration (config.py)

Centralised configuration module reading all settings from environment variables with sensible defaults. No AWS credentials stored — relies on boto3 default credential chain.

**Key settings:**
- AWS_REGION (default: ap-south-1), BEDROCK_REGION (default: us-east-1)
- CATALOG_TABLE (default: qm_catalog), MEMORY_TABLE (default: qm_memory)
- BEDROCK_MODEL_ID (default: us.amazon.nova-pro-v1:0) — used for the agentic loop
- BEDROCK_FAST_MODEL_ID (default: us.amazon.nova-lite-v1:0) — used for intent classification
- MAX_AGENT_ITERATIONS (10), CART_MAX_ITEMS (12), AGENT_TIMEOUT_SECONDS (30)

### 2. Database Layer (db/)

#### Catalog Interface (db/catalog.py)

- `search_by_tags(tags: list[str], max_results: int = 20) -> list[Product]` — paginated scan with OR filter across tags, in_stock filter, sorted by match count descending, capped at max_results
- `get_by_ids(product_ids: list[str]) -> list[Product]` — batch_get_item with retry for unprocessed keys, preserving input order
- `get_all_in_category(category: str) -> list[Product]` — filtered scan for in-stock products
- `get_all_categories() -> list[str]` — scan returning unique category values
- All operations wrapped in try/except raising `CatalogError`

#### Memory Interface (db/memory.py)

- `get_user_memory(user_id: str) -> dict` — returns preferences, exclusions, past_orders (empty defaults for new users)
- `update_memory(user_id: str, cart: Cart) -> None` — appends order, caps at 10 most recent
- `get_frequent_products(user_id: str, top_n: int = 5) -> list[str]` — Counter-based frequency analysis
- All operations wrapped in try/except raising `MemoryError`

### 3. Agent Layer (agent/)

#### Intent Classifier Interface (agent/intent_classifier.py)

- `classify_intent(user_intent: str) -> IntentMode` — single fast Bedrock call, returns enum value, defaults to INTENT_BASED on error

#### Tools Interface (agent/tools.py)

- `get_tool_config() -> dict` — returns toolConfig payload for Converse API
- `execute_tool(tool_name: str, tool_input: dict, user_id: str, budget: float) -> str` — dispatcher returning JSON string

#### Bedrock Agent Interface (agent/bedrock_agent.py)

- `run_agent(user_intent: str, budget: float, user_id: str, cart_state: dict | None = None, change_request: str | None = None) -> Cart` — full agentic loop

#### Cart Builder Interface (agent/cart_builder.py)

- `build_cart_from_candidates(candidates: list[Product], budget: float, quantities: dict[str, int], user_id: str, justifications: dict[str, str], intent: str = "") -> Cart` — greedy knapsack builder

### 4. Frontend (app.py)

Streamlit application exposing:
- `_build_cart_action(intent: str, budget: float) -> None` — triggers new cart build via run_agent
- `_update_cart_action(change_request: str) -> None` — triggers change loop via run_agent
- `_get_cart() -> Cart | None` — deserialises from session state
- `_store_cart(cart: Cart | None) -> None` — serialises to session state

## Data Models

### Product

```python
@dataclass
class Product:
    product_id: str
    name: str
    category: str       # "Grocery", "Beverages", "Snacks", "Household", "Fresh & Ready"
    price: float        # INR
    tags: list[str]     # semantic tags for search
    in_stock: bool
    unit: str           # "500g", "1L", "pack of 6", "dozen"
    relevance_score: float = 0.0  # set by agent (0-100)
```

### CartItem

```python
@dataclass
class CartItem:
    product: Product
    quantity: int
    justification: str   # one-sentence reason
    line_total: float    # price * quantity (auto-calculated in __post_init__)
```

### Cart

```python
@dataclass
class Cart:
    items: list[CartItem]
    budget: float
    total: float              # sum of line_totals
    remaining_budget: float   # budget - total
    user_id: str
    intent: str               # original user input
    timestamp: str            # ISO format
```

### IntentMode (Enum)

```python
class IntentMode(Enum):
    FRICTIONLESS = "frictionless"
    INTENT_BASED = "intent_based"
    PREDICTIVE = "predictive"
```

### DynamoDB Table Schemas

**qm_catalog** — Partition key: `product_id` (String), Billing: PAY_PER_REQUEST
**qm_memory** — Partition key: `user_id` (String), Billing: PAY_PER_REQUEST

## Error Handling

### Custom Exception Hierarchy

- `CatalogError` — raised by db/catalog.py on any DynamoDB ClientError
- `MemoryError` — raised by db/memory.py on any DynamoDB ClientError
- `AgentError` — raised by bedrock_agent.py on Bedrock failures or missing cart
- `AgentTimeoutError(AgentError)` — raised when loop exceeds MAX_AGENT_ITERATIONS
- `CartBudgetError` — raised by cart_builder.py if final total > budget (should never happen due to greedy algorithm, but serves as a safety net)

### Error Flow

1. Database layer: catches `botocore.exceptions.ClientError`, raises domain-specific error with context
2. Tools layer: catches all exceptions in `execute_tool`, returns error JSON to the agent model
3. Agent layer: catches `ClientError` from Bedrock, raises `AgentError`; validates cart budget on end_turn
4. Frontend: catches all exceptions from `run_agent`, stores error message in session state, displays via `st.error()`
5. Checkout: catches memory update failure, shows `st.warning()` but still confirms order

## Testing Strategy

### Property-Based Tests (Hypothesis)

Property-based tests validate invariants that must hold for all valid inputs:

1. **Budget invariant** — cart.total <= budget for any product list and positive budget
2. **Item count bound** — len(cart.items) <= CART_MAX_ITEMS for any input
3. **No out-of-stock** — every cart item has in_stock == True
4. **Non-empty justification** — every CartItem.justification has len > 0
5. **Greedy ordering** — cart items in non-increasing effective_score order
6. **Product dict round-trip** — from_dict(to_dict(p)) == p
7. **Product DynamoDB round-trip** — from_dynamo_item(to_dynamo_item(p)) ≈ p (within 1e-6)
8. **CartItem dict round-trip** — from_dict(to_dict(item)) == item
9. **Cart dict round-trip** — from_dict(to_dict(cart)) ≈ cart

### Integration Tests (manual validation)

Four demo scenarios serve as integration smoke tests:
1. "Quick dinner for 4 people" + ₹500 → 5-9 items, total <= 500
2. "Birthday party snacks" + ₹1000 → mix of snacks + beverages
3. "I need eggs and bread" + ₹200 → exact products, no extras
4. Cart change "remove dairy products" → dairy removed, rest preserved

## Correctness Properties

### Property 1: Budget Invariant

**Validates: Requirements 3.2, 3.5**

For all non-empty lists of candidate products and all budgets > 0, `build_cart_from_candidates` SHALL produce a cart where `cart.total <= budget`. This property holds regardless of product prices, relevance scores, or quantities.

### Property 2: Cart Item Count Bound

**Validates: Requirements 3.7**

For all inputs to `build_cart_from_candidates`, the resulting cart SHALL have at most CART_MAX_ITEMS (12) items.

### Property 3: No Out-of-Stock Products

**Validates: Requirements 3.8**

For all inputs, every product in the resulting cart SHALL have `in_stock == True`.

### Property 4: Non-Empty Justification Invariant

**Validates: Requirements 4.1**

For all carts produced by `build_cart_from_candidates`, every CartItem SHALL have a `justification` string with length > 0.

### Property 5: Cart Serialisation Round-Trip

**Validates: Requirements 12.1**

For all valid Cart objects, `Cart.from_dict(cart.to_dict())` SHALL produce a Cart with equivalent items, budget, total, and remaining_budget.

### Property 6: Product Dict Round-Trip

**Validates: Requirements 12.2**

For all valid Product objects, `Product.from_dict(product.to_dict())` SHALL produce a Product with identical field values.

### Property 7: Product DynamoDB Round-Trip

**Validates: Requirements 12.4**

For all valid Product objects, `Product.from_dynamo_item(product.to_dynamo_item())` SHALL produce a Product with equivalent field values (float precision tolerance of 1e-6).

### Property 8: CartItem Round-Trip

**Validates: Requirements 12.3**

For all valid CartItem objects, `CartItem.from_dict(item.to_dict())` SHALL produce a CartItem with identical product, quantity, justification, and line_total.

### Property 9: Greedy Ordering

**Validates: Requirements 3.1**

For all carts produced by `build_cart_from_candidates` with at least 2 items, the items SHALL appear in non-increasing order of `relevance_score / price` (within floating-point tolerance).

### Property 10: Quantity Degradation

**Validates: Requirements 3.3**

For any product that appears in the cart with quantity < desired_quantity, the desired quantity at the original amount would have exceeded the remaining budget at that point.

### Property 11: Memory Cap

**Validates: Requirements 5.5**

After any number of `update_memory` calls for a single user, `get_user_memory` SHALL return at most 10 past_orders.

### Property 12: Catalog Search Tag Match

**Validates: Requirements 7.1**

For all results from `search_by_tags`, every returned product SHALL have `in_stock == True` and contain at least one tag from the search input.

### Property 13: Catalog Search Result Ordering

**Validates: Requirements 7.2**

For all results from `search_by_tags`, the match-count of consecutive products SHALL be in non-increasing order.

### Property 14: Catalog Search Result Limit

**Validates: Requirements 7.3**

For all calls to `search_by_tags(tags, max_results=N)`, `len(results) <= N`.

## Technology Choices

| Component | Technology | Rationale |
|-----------|-----------|-----------|
| Frontend | Streamlit | Rapid prototyping, Python-native, sufficient for hackathon demo |
| AI Engine | AWS Bedrock (Amazon Nova Pro) | Tool-use support, fast inference, managed service, no Marketplace subscription needed |
| Fast Classifier | AWS Bedrock (Amazon Nova Lite) | Low latency for simple classification |
| Database | Amazon DynamoDB | Serverless, low-latency, simple key-value access pattern |
| Language | Python 3.11+ | Team familiarity, rich AWS SDK (boto3), Streamlit compatibility |

## Constraints and Assumptions

- The system targets a hackathon demo with a single concurrent user (no multi-tenancy)
- Product catalog is seeded once with 50 items; no CRUD admin interface needed
- Budget is in INR (₹), integer slider increments of ₹50
- The Bedrock agent uses temperature 0.2 for deterministic-ish responses
- Maximum end-to-end response time target: 10 seconds (dependent on Bedrock latency)
- No authentication layer — uses a hardcoded demo_user_id by default
