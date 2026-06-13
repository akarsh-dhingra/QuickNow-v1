"""Fast intent-mode classification using a small Bedrock model."""

from __future__ import annotations

import logging
from enum import Enum

import boto3
from botocore.exceptions import ClientError

import config

logger = logging.getLogger("amazon_now.intent_classifier")


class IntentMode(Enum):
    FRICTIONLESS = "frictionless"  # user knows exact item: "get me Amul butter"
    INTENT_BASED = "intent_based"  # user knows outcome: "dinner for 4 people"
    PREDICTIVE = "predictive"      # user is uncertain: "I think I need something"


_SYSTEM_PROMPT = (
    "Classify this shopping intent into exactly one of these three modes:\n"
    "FRICTIONLESS - user knows the exact product name they want\n"
    "INTENT_BASED - user describes an outcome or occasion, not specific products\n"
    "PREDICTIVE - user is unsure, vague, or asking for recommendations\n"
    "Respond with only the mode name in uppercase, nothing else."
)

_MODE_BY_NAME = {
    "FRICTIONLESS": IntentMode.FRICTIONLESS,
    "INTENT_BASED": IntentMode.INTENT_BASED,
    "PREDICTIVE": IntentMode.PREDICTIVE,
}


def _client():
    return boto3.client("bedrock-runtime", region_name=config.BEDROCK_REGION)


def classify_intent(user_intent: str) -> IntentMode:
    """Classify ``user_intent`` into an :class:`IntentMode`.

    Uses a single fast (Haiku) Bedrock call with no tools. Defaults to
    ``INTENT_BASED`` on any error or unparseable response.
    """
    try:
        response = _client().converse(
            modelId=config.BEDROCK_FAST_MODEL_ID,
            system=[{"text": _SYSTEM_PROMPT}],
            messages=[
                {"role": "user", "content": [{"text": user_intent}]}
            ],
            inferenceConfig={"maxTokens": 16, "temperature": 0.0},
        )
        text = (
            response["output"]["message"]["content"][0]["text"]
            .strip()
            .upper()
        )
    except (ClientError, KeyError, IndexError) as exc:
        logger.warning("Intent classification failed, defaulting: %s", exc)
        return IntentMode.INTENT_BASED

    # Tolerate extra punctuation/words by scanning for a known token.
    for name, mode in _MODE_BY_NAME.items():
        if name in text:
            return mode

    return IntentMode.INTENT_BASED
