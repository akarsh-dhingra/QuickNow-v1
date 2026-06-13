# Requirements Document

## Introduction

QuickMind is a full-stack, intent-driven AI shopping agent for Amazon's quick-commerce platform. It eliminates browsing by accepting a natural-language intent and budget, then using an AWS Bedrock AI agent to classify the intent, query a DynamoDB product catalog, apply budget constraints via a greedy knapsack algorithm, read user purchase history, and return a ready-to-checkout cart. The customer can refine the cart conversationally without rebuilding it from scratch.

## Glossary

- **QuickMind_Agent**: The core AWS Bedrock-powered agentic loop that orchestrates tool calls (search_catalog, get_user_memory, build_cart) to produce a shopping cart.
- **Intent_Classifier**: A lightweight Bedrock model call that classifies user input into one of three intent modes (FRICTIONLESS, INTENT_BASED, PREDICTIVE).
- **Cart_Builder**: The greedy knapsack algorithm module that selects products within a budget constraint using a relevance_score/price ratio.
- **Catalog_Store**: The DynamoDB table (qm_catalog) holding 50 Indian quick-commerce products across 5 categories with tags and pricing.
- **Memory_Store**: The DynamoDB table (qm_memory) holding user purchase history, preferences, and exclusions.
- **Cart**: A data object containing a list of CartItems, a budget, a computed total, and remaining budget.
- **CartItem**: A line item in a Cart consisting of a Product, quantity, justification string, and line total.
- **Product**: A catalog entry with product_id, name, category, price, tags, in_stock flag, and unit.
- **Streamlit_UI**: The frontend application providing intent input, budget slider, cart display, and conversational refinement.
- **Change_Loop**: The conversational refinement flow where a user modifies an existing cart without full rebuild.
- **Budget**: A numeric value in INR (₹) representing the maximum allowed cart total.

## Requirements

### Requirement 1: Intent Classification

**User Story:** As a customer, I want my natural-language shopping request classified into an intent mode, so that the agent can tailor its search and selection strategy.

#### Acceptance Criteria

1. WHEN a customer submits a shopping intent, THE Intent_Classifier SHALL classify the intent into exactly one of FRICTIONLESS, INTENT_BASED, or PREDICTIVE modes.
2. WHEN the intent contains an exact product name (e.g., "get me Amul butter"), THE Intent_Classifier SHALL classify the intent as FRICTIONLESS.
3. WHEN the intent describes an outcome or occasion (e.g., "dinner for 4 people"), THE Intent_Classifier SHALL classify the intent as INTENT_BASED.
4. WHEN the intent is vague or uncertain (e.g., "I think I need something"), THE Intent_Classifier SHALL classify the intent as PREDICTIVE.
5. IF the classification call to Bedrock fails, THEN THE Intent_Classifier SHALL default to INTENT_BASED mode.

### Requirement 2: Agentic Tool-Use Loop

**User Story:** As a customer, I want the AI agent to iteratively search products, read my history, and build a cart, so that I receive a personalised and budget-respecting cart without manual browsing.

#### Acceptance Criteria

1. WHEN the QuickMind_Agent receives a user intent and budget, THE QuickMind_Agent SHALL invoke get_user_memory to retrieve preferences, exclusions, and past orders before searching the catalog.
2. WHEN the QuickMind_Agent searches for products, THE QuickMind_Agent SHALL call search_catalog with tags derived from the user intent.
3. WHEN the QuickMind_Agent has identified candidate products, THE QuickMind_Agent SHALL call build_cart with product_ids, relevance_scores, justifications, and the budget.
4. THE QuickMind_Agent SHALL complete the full agentic loop within a maximum of 10 iterations.
5. IF the QuickMind_Agent exceeds 10 iterations without producing a cart, THEN THE QuickMind_Agent SHALL raise an AgentTimeoutError.
6. IF a Bedrock API call fails, THEN THE QuickMind_Agent SHALL raise an AgentError with the failure details.
7. THE QuickMind_Agent SHALL terminate the loop when the model signals end_turn and a cart has been built.

### Requirement 3: Budget-Constrained Cart Building

**User Story:** As a customer, I want my cart total to never exceed my stated budget, so that I can trust the agent to respect my spending limit.

#### Acceptance Criteria

1. THE Cart_Builder SHALL select products using a greedy knapsack algorithm that ranks candidates by relevance_score divided by price in descending order.
2. THE Cart_Builder SHALL add products to the cart only when the cumulative total does not exceed the budget.
3. WHEN a candidate product's desired quantity would exceed the remaining budget, THE Cart_Builder SHALL reduce the quantity down to the maximum that fits within the remaining budget.
4. WHEN a candidate product does not fit the remaining budget even at quantity 1, THE Cart_Builder SHALL skip that product.
5. THE Cart_Builder SHALL enforce a hard constraint that the cart total is less than or equal to the budget.
6. IF the completed cart total exceeds the budget, THEN THE Cart_Builder SHALL raise a CartBudgetError.
7. THE Cart_Builder SHALL limit the cart to a maximum of 12 items.
8. THE Cart_Builder SHALL skip products that are not in stock.

### Requirement 4: Cart Item Justification

**User Story:** As a customer, I want every item in my cart to include a reason for its selection, so that I understand why the agent chose each product.

#### Acceptance Criteria

1. THE Cart_Builder SHALL assign a non-empty justification string to every CartItem in the cart.
2. WHEN the QuickMind_Agent provides a justification for a product, THE Cart_Builder SHALL use that agent-provided justification.
3. WHEN the QuickMind_Agent does not provide a justification for a product, THE Cart_Builder SHALL generate a default justification containing the product price and unit.

### Requirement 5: User Memory and Personalisation

**User Story:** As a returning customer, I want the agent to remember my past orders, preferences, and exclusions, so that my cart is personalised to my habits.

#### Acceptance Criteria

1. WHEN the QuickMind_Agent processes a request for a user, THE QuickMind_Agent SHALL retrieve preferences, exclusions, and past orders from the Memory_Store.
2. WHEN the Memory_Store contains exclusions for a user, THE QuickMind_Agent SHALL exclude products matching those exclusions from the cart.
3. WHEN the Memory_Store contains past orders for a user, THE QuickMind_Agent SHALL prioritise frequently ordered products when relevant to the current intent.
4. WHEN a customer completes checkout, THE Memory_Store SHALL append the order to the user's past_orders list.
5. THE Memory_Store SHALL retain a maximum of 10 past orders per user, keeping only the most recent orders.
6. IF the Memory_Store lookup fails, THEN THE Memory_Store SHALL raise a MemoryError with the failure details.
7. WHEN a user has no prior history, THE Memory_Store SHALL return an empty-but-valid structure with empty preferences, exclusions, and past_orders lists.

### Requirement 6: Conversational Cart Refinement (Change Loop)

**User Story:** As a customer, I want to modify my existing cart by describing a change in natural language, so that I can refine my order without rebuilding from scratch.

#### Acceptance Criteria

1. WHEN a customer submits a change request against an existing cart, THE QuickMind_Agent SHALL receive both the existing cart state and the change request.
2. WHEN processing a change request, THE QuickMind_Agent SHALL preserve all cart items that are not affected by the change request.
3. WHEN processing a change request, THE QuickMind_Agent SHALL search for and replace only the items that need to change.
4. WHEN the change request is "remove dairy products", THE QuickMind_Agent SHALL remove all items with dairy-related tags while preserving all remaining items.
5. THE QuickMind_Agent SHALL enforce the budget constraint on the modified cart using the same rules as new cart construction.

### Requirement 7: Product Catalog Search

**User Story:** As a customer, I want the agent to search a product catalog by relevant tags, so that it finds products matching my intent.

#### Acceptance Criteria

1. WHEN the search_catalog tool is invoked with tags, THE Catalog_Store SHALL return in-stock products matching any of the provided tags.
2. THE Catalog_Store SHALL sort results by the number of matching tags in descending order.
3. THE Catalog_Store SHALL limit results to a configurable maximum (default 20 products).
4. WHEN a category filter is provided, THE Catalog_Store SHALL return only products within that category.
5. IF the DynamoDB scan fails, THEN THE Catalog_Store SHALL raise a CatalogError with the failure details.
6. THE Catalog_Store SHALL support paginated scans to retrieve all matching products regardless of DynamoDB page limits.

### Requirement 8: DynamoDB Product Catalog Data

**User Story:** As a system operator, I want a seeded catalog of 50 realistic Indian quick-commerce products across 5 categories, so that the agent has a representative dataset to work with.

#### Acceptance Criteria

1. THE Catalog_Store SHALL contain 50 products distributed across 5 categories: Grocery, Beverages, Snacks, Household, and Fresh & Ready.
2. THE Catalog_Store SHALL store each Product with product_id, name, category, price (in INR), tags, in_stock flag, and unit fields.
3. THE Catalog_Store SHALL store prices as DynamoDB Decimal type and convert to float on retrieval.

### Requirement 9: Streamlit UI — Intent Input and Cart Display

**User Story:** As a customer, I want a web interface where I can type my intent, set a budget, view my cart, and refine it conversationally.

#### Acceptance Criteria

1. THE Streamlit_UI SHALL provide a text area for entering a natural-language shopping intent.
2. THE Streamlit_UI SHALL provide a slider for setting the budget between ₹50 and ₹2000 in ₹50 increments.
3. THE Streamlit_UI SHALL display a "Build My Cart" button that triggers cart construction.
4. WHEN a cart is built, THE Streamlit_UI SHALL display each CartItem as a card showing product name, unit, quantity, category, line total, and justification.
5. WHEN a cart is built, THE Streamlit_UI SHALL display a budget progress bar showing total spent relative to budget.
6. THE Streamlit_UI SHALL display the remaining budget in green when positive and in red when zero or negative.
7. THE Streamlit_UI SHALL provide a text input and "Update Cart" button for submitting change requests against the existing cart.
8. THE Streamlit_UI SHALL provide a "Checkout" button that saves the order to user memory and confirms placement.
9. THE Streamlit_UI SHALL provide example intent chips ("Dinner for 4, ₹500", "Birthday party, ₹1000", "Quick breakfast, ₹200") that pre-fill the intent and budget.
10. THE Streamlit_UI SHALL display a per-item remove button that removes the item and recalculates the cart total.

### Requirement 10: Error Handling and Resilience

**User Story:** As a customer, I want the application to handle failures gracefully, so that errors are surfaced clearly without crashing.

#### Acceptance Criteria

1. THE QuickMind_Agent SHALL wrap all AWS Bedrock API calls in try/except and raise AgentError on failure.
2. THE Catalog_Store SHALL wrap all DynamoDB operations in try/except and raise CatalogError on failure.
3. THE Memory_Store SHALL wrap all DynamoDB operations in try/except and raise MemoryError on failure.
4. IF an error occurs during cart building or update, THEN THE Streamlit_UI SHALL display the error message to the customer.
5. IF the memory update fails at checkout, THEN THE Streamlit_UI SHALL display a warning but still confirm the order placement.

### Requirement 11: Security and Configuration

**User Story:** As a system operator, I want all configuration externalised and no credentials hardcoded, so that the system is secure and portable across environments.

#### Acceptance Criteria

1. THE config module SHALL read all AWS region, table name, model ID, and behaviour settings from environment variables with sensible defaults.
2. THE config module SHALL contain zero hardcoded AWS credentials.
3. THE QuickMind_Agent SHALL rely on the boto3 default credential chain for all AWS authentication.

### Requirement 12: Cart Serialisation Round-Trip

**User Story:** As a developer, I want Cart and Product objects to serialise to dict and deserialise back without data loss, so that carts can be stored in session state and passed between components reliably.

#### Acceptance Criteria

1. FOR ALL valid Cart objects, serialising via to_dict then deserialising via from_dict SHALL produce a Cart with equivalent items, budget, total, and remaining_budget values (round-trip property).
2. FOR ALL valid Product objects, serialising via to_dict then deserialising via from_dict SHALL produce a Product with identical field values (round-trip property).
3. FOR ALL valid CartItem objects, serialising via to_dict then deserialising via from_dict SHALL produce a CartItem with identical product, quantity, justification, and line_total values (round-trip property).
4. FOR ALL valid Product objects, serialising via to_dynamo_item then deserialising via from_dynamo_item SHALL produce a Product with equivalent field values (round-trip property).
