# QuickMind — AI Shopping Agent

**Amazon Now** is an intent-driven AI shopping agent for Amazon's quick-commerce
platform. A customer types a natural-language intent ("Quick dinner for 4
people, budget ₹500") and clicks one button. An AWS Bedrock agent classifies the
intent, queries a DynamoDB catalog, applies a greedy knapsack budget
optimisation, reads the user's purchase history, and returns a ready-to-checkout
cart — which can then be refined conversationally.

## Architecture

```
┌─────────────────────────────────────────────────┐
│           Streamlit Frontend (app.py)            │
│  [Intent Input] [Budget Slider] [Build Cart →]   │
│  [Cart Panel with items + justifications]        │
│  [Conversational change input at bottom]         │
└────────────────────┬────────────────────────────┘
                     │ HTTP (local)
                     ▼
┌─────────────────────────────────────────────────┐
│         AWS Bedrock Agent (Claude 3.5)           │
│  bedrock_agent.py — full tool-use agentic loop   │
│  ┌──────────────┐  ┌──────────────────────────┐ │
│  │Intent        │  │Cart Builder              │ │
│  │Classifier    │  │(greedy knapsack)         │ │
│  └──────────────┘  └──────────────────────────┘ │
└───────┬─────────────────────┬───────────────────┘
        │                     │
        ▼                     ▼
┌───────────────┐    ┌────────────────────┐
│ DynamoDB      │    │ DynamoDB           │
│ qm_catalog    │    │ qm_memory          │
│ (50 products) │    │ (user history)     │
└───────────────┘    └────────────────────┘
        │                     │
        └──────────┬──────────┘
                   ▼
        ┌──────────────────┐
        │   Cart Object    │
        │ items, total,    │
        │ justifications   │
        └──────────────────┘
                   │
                   ▼ (change loop)
        ┌──────────────────┐
        │ Conversational   │
        │ Edit Resolution  │
        │ (partial re-run) │
        └──────────────────┘
```

## Setup

### Prerequisites
- Python 3.11+
- AWS account with Bedrock access (Claude 3.5 Sonnet enabled in `us-east-1`)
- AWS credentials configured (`aws configure` or environment variables)

### Install
```bash
pip install -r requirements.txt
```

### Create DynamoDB Tables & Seed Data
```bash
python db/seed_catalog.py
```

### Run
```bash
streamlit run app.py
```

## Configuration

All settings live in `config.py` and can be overridden with environment
variables: `AWS_REGION`, `BEDROCK_REGION`, `BEDROCK_MODEL_ID`,
`CATALOG_TABLE`, `MEMORY_TABLE`, `DEFAULT_USER_ID`, `MAX_AGENT_ITERATIONS`,
`CART_MAX_ITEMS`, `AGENT_TIMEOUT_SECONDS`.

DynamoDB defaults to `ap-south-1`; Bedrock defaults to `us-east-1`.

## Demo Scenarios
Try these intents to see QuickMind in action:
1. "Quick dinner for 4 people" with ₹500 budget
2. "Birthday party snacks and drinks" with ₹1000 budget
3. "Morning breakfast essentials" with ₹300 budget
4. "I need eggs and bread" with ₹150 budget (Frictionless mode)

After a cart is built, try:
- "Remove dairy products"
- "Add something for dessert"
- "Swap paneer for something cheaper"

## AWS IAM Permissions (minimum policy)

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "BedrockInvoke",
      "Effect": "Allow",
      "Action": [
        "bedrock:InvokeModel",
        "bedrock:Converse"
      ],
      "Resource": [
        "arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-3-5-sonnet-20241022-v2:0",
        "arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-3-haiku-20240307-v1:0"
      ]
    },
    {
      "Sid": "DynamoDBAccess",
      "Effect": "Allow",
      "Action": [
        "dynamodb:CreateTable",
        "dynamodb:DescribeTable",
        "dynamodb:ListTables",
        "dynamodb:PutItem",
        "dynamodb:GetItem",
        "dynamodb:BatchGetItem",
        "dynamodb:BatchWriteItem",
        "dynamodb:UpdateItem",
        "dynamodb:Scan"
      ],
      "Resource": [
        "arn:aws:dynamodb:ap-south-1:*:table/qm_catalog",
        "arn:aws:dynamodb:ap-south-1:*:table/qm_memory"
      ]
    }
  ]
}
```

## Known Limitations & Future Work
- Catalog uses DynamoDB scan (production: OpenSearch for semantic search)
- Single user demo (production: auth layer + per-user DynamoDB partition)
- No real payment integration
- Future: voice input, predictive re-order notifications, multi-retailer price arbitrage
