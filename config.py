"""Central configuration for the Amazon Now / QuickMind shopping agent.

All values can be overridden via environment variables so the same code runs
locally and on AWS Lambda without modification. No AWS credentials are ever
stored here — boto3's default credential chain is used everywhere.
"""

import os

# --- DynamoDB ---------------------------------------------------------------
AWS_REGION = os.getenv("AWS_REGION", "ap-south-1")
CATALOG_TABLE = os.getenv("CATALOG_TABLE", "qm_catalog")
MEMORY_TABLE = os.getenv("MEMORY_TABLE", "qm_memory")

# --- Bedrock ----------------------------------------------------------------
# Bedrock region may differ from the DynamoDB region (Claude 3.5 Sonnet is in
# us-east-1 for most accounts).
BEDROCK_REGION = os.getenv("BEDROCK_REGION", "us-east-1")
# Amazon Nova models are first-party (not sold via AWS Marketplace), so they
# work on AWS India / UPI accounts that can't complete Marketplace
# subscriptions required by Anthropic Claude models. Served via cross-region
# inference profiles (the "us." prefix).
BEDROCK_MODEL_ID = os.getenv(
    "BEDROCK_MODEL_ID", "us.amazon.nova-pro-v1:0"
)
# A small, fast model used purely for intent classification.
BEDROCK_FAST_MODEL_ID = os.getenv(
    "BEDROCK_FAST_MODEL_ID", "us.amazon.nova-lite-v1:0"
)

# --- Agent behaviour --------------------------------------------------------
DEFAULT_USER_ID = os.getenv("DEFAULT_USER_ID", "demo_user")
MAX_AGENT_ITERATIONS = int(os.getenv("MAX_AGENT_ITERATIONS", "10"))
CART_MAX_ITEMS = int(os.getenv("CART_MAX_ITEMS", "12"))
AGENT_TIMEOUT_SECONDS = int(os.getenv("AGENT_TIMEOUT_SECONDS", "30"))
