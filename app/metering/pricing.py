from __future__ import annotations

# USD per 1,000 tokens, as (input_price, output_price).
# These are illustrative and drift over time — treat them as configuration, not
# gospel. The point is a consistent basis for "cost spent" and "cost saved".
PRICING: dict[str, tuple[float, float]] = {
    "gpt-4o": (0.0025, 0.0100),
    "gpt-4o-mini": (0.00015, 0.0006),
    "gpt-4-turbo": (0.0100, 0.0300),
    "gpt-3.5-turbo": (0.0005, 0.0015),
    "claude-3-5-sonnet": (0.0030, 0.0150),
    "claude-3-5-haiku": (0.0008, 0.0040),
}

# Fallback for unknown / mock models so cost math never crashes.
DEFAULT_PRICE: tuple[float, float] = (0.0005, 0.0015)


def price_for(model: str) -> tuple[float, float]:
    if model in PRICING:
        return PRICING[model]
    # Match dated ids like "gpt-4o-2024-08-06" against their base name.
    for name, price in PRICING.items():
        if model.startswith(name):
            return price
    return DEFAULT_PRICE
