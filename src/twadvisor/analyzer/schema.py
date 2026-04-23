"""Structured output tool definitions for analyzers."""

RECOMMENDATION_TOOL_SCHEMA = {
    "name": "submit_recommendations",
    "description": "Submit Taiwan stock recommendations in structured form",
    "input_schema": {
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
                        "qty": {"type": "integer"},
                        "order_type": {"enum": ["limit", "market"]},
                        "price": {"type": "number"},
                        "stop_loss": {"type": "number"},
                        "take_profit": {"type": "number"},
                        "reason": {"type": "string"},
                        "confidence": {"type": "number"},
                    },
                    "required": ["symbol", "action", "reason", "confidence"],
                },
            },
            "warnings": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["market_view", "recommendations"],
    },
}
