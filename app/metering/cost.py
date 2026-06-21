from __future__ import annotations

from .pricing import price_for


def compute_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Cost in USD for a single completion, from its token usage.

    On a cache MISS this is the actual money spent. On a cache HIT this same
    figure is the money *saved* — what the provider call would have cost.
    """
    in_price, out_price = price_for(model)
    return (prompt_tokens / 1000.0) * in_price + (completion_tokens / 1000.0) * out_price
