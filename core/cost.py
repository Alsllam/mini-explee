"""Rough cost estimates from token counts.

Prices change often and differ by provider, region and deployment type, so
treat these numbers as estimates and check your provider's pricing page.
Override them in .env if you know yours:
    PRICE_INPUT_PER_M=0.15   PRICE_CACHED_PER_M=0.075   PRICE_OUTPUT_PER_M=0.60

The Batch API costs about half (lesson 4.4). Cached input tokens (lesson 2.4)
cost less than normal input tokens.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

# USD per 1M tokens, public list prices known as of mid-2026 (approximate).
KNOWN_PRICES = {
    "gpt-4o-mini": (0.15, 0.075, 0.60),
    "gpt-4.1-mini": (0.40, 0.10, 1.60),
    "gpt-4o": (2.50, 1.25, 10.00),
}
BATCH_DISCOUNT = 0.5


@dataclass
class Usage:
    input_tokens: int = 0
    cached_tokens: int = 0
    output_tokens: int = 0
    requests: int = 0

    def add(self, input_tokens: int, cached_tokens: int, output_tokens: int) -> None:
        self.input_tokens += input_tokens or 0
        self.cached_tokens += cached_tokens or 0
        self.output_tokens += output_tokens or 0
        self.requests += 1

    @property
    def cache_share(self) -> float:
        return self.cached_tokens / self.input_tokens if self.input_tokens else 0.0


def prices_for(model_name: str) -> tuple[float, float, float]:
    """(input, cached input, output) USD per 1M tokens."""
    env = [os.getenv(k) for k in ("PRICE_INPUT_PER_M", "PRICE_CACHED_PER_M", "PRICE_OUTPUT_PER_M")]
    if all(env):
        return tuple(float(v) for v in env)  # type: ignore[return-value]
    # Azure deployment names may differ from model names; match what we can.
    for name, prices in KNOWN_PRICES.items():
        if name in model_name:
            return prices
    return KNOWN_PRICES["gpt-4o-mini"]


def estimate_usd(usage: Usage, model_name: str, batch: bool = False) -> float:
    price_in, price_cached, price_out = prices_for(model_name)
    uncached = usage.input_tokens - usage.cached_tokens
    cost = (uncached * price_in + usage.cached_tokens * price_cached + usage.output_tokens * price_out) / 1e6
    return cost * (BATCH_DISCOUNT if batch else 1.0)
