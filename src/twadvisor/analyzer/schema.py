"""Structured output schemas for analyzers."""

from __future__ import annotations

from copy import deepcopy

RECOMMENDATION_RESPONSE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "market_view": {"type": "string", "description": "Traditional Chinese market summary under 100 characters"},
        "recommendations": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "symbol": {"type": "string", "pattern": "^[0-9]{4,6}$"},
                    "action": {"enum": ["buy", "sell", "hold", "watch"]},
                    "qty": {"type": "integer", "description": "Order quantity in shares. Use 1000-share lots unless explicitly recommending odd lots."},
                    "order_type": {"enum": ["limit", "market"], "description": "Prefer limit orders unless a market order is explicitly justified."},
                    "price": {"type": "number", "description": "Suggested executable order price, not merely the latest close."},
                    "stop_loss": {"type": "number", "description": "Suggested stop-loss price for buy/sell actions."},
                    "take_profit": {"type": "number", "description": "Suggested take-profit price for buy/sell actions."},
                    "reason": {"type": "string", "description": "Traditional Chinese reason including order price, lot sizing, stop-loss, and take-profit rationale."},
                    "confidence": {"type": "number"},
                },
                "required": ["symbol", "action", "reason", "confidence"],
            },
        },
        "warnings": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["market_view", "recommendations"],
}

RECOMMENDATION_TOOL_SCHEMA = {
    "name": "submit_recommendations",
    "description": "Submit Taiwan stock recommendations in structured form",
    "input_schema": RECOMMENDATION_RESPONSE_SCHEMA,
}


def gemini_response_schema() -> dict:
    """Return a Gemini-compatible response schema with explicit property ordering."""

    schema = deepcopy(RECOMMENDATION_RESPONSE_SCHEMA)
    _apply_property_ordering(schema)
    return schema


def _apply_property_ordering(node: dict) -> None:
    """Recursively add property ordering for Gemini JSON schema."""

    if node.get("type") == "object" and "properties" in node:
        node["propertyOrdering"] = list(node["properties"].keys())
        for child in node["properties"].values():
            if isinstance(child, dict):
                _apply_property_ordering(child)
    items = node.get("items")
    if isinstance(items, dict):
        _apply_property_ordering(items)
