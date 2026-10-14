"""Price book: USD per million tokens, per model. Overridable, so any model can be priced.

When a provider reports the billed cost (``ProviderResponse.cost_usd``), that
number wins. Otherwise the price book computes it from token usage. A model
with no price and no reported cost is charged at ``fallback`` so the budget
never treats calls as free.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Price:
    input: float
    output: float
    cache_read: float | None = None
    cache_write: float | None = None
    long_input: float | None = None  # price tier above ``long_threshold`` prompt tokens
    long_output: float | None = None
    long_threshold: int = 100_000

    @property
    def cache_read_price(self) -> float:
        return self.cache_read if self.cache_read is not None else self.input * 0.1

    @property
    def cache_write_price(self) -> float:
        return self.cache_write if self.cache_write is not None else self.input * 1.25


DEFAULT_PRICES: dict[str, Price] = {
    "claude-opus-5-5": Price(input=4.00, output=20.00, cache_read=0.20),
    "claude-sonnet-5-5": Price(input=2.00, output=10.00, cache_read=0.20),
    "claude-haiku-5-5": Price(input=0.10, output=0.50, cache_read=0.01, long_input=0.50, long_output=2.50),
}

# Deliberately pessimistic: an unpriced model should hit its budget early, not never.
FALLBACK_PRICE = Price(input=15.00, output=75.00)


class PriceBook:
    def __init__(self, prices: dict[str, Price] | None = None, fallback: Price = FALLBACK_PRICE):
        self.prices = dict(DEFAULT_PRICES)
        if prices:
            self.prices.update(prices)
        self.fallback = fallback

    @classmethod
    def from_json(cls, path: str) -> PriceBook:
        with open(path) as f:
            data: dict[str, dict[str, Any]] = json.load(f)
        return cls({m: Price(**p) for m, p in data.items()})

    def price(self, model: str) -> Price:
        return self.prices.get(model, self.fallback)

    def _tier(self, p: Price, prompt_tokens: int) -> tuple[float, float, float]:
        if p.long_input is not None and prompt_tokens > p.long_threshold:
            return p.long_input, p.long_output or p.output, p.long_input / p.input
        return p.input, p.output, 1.0

    def cost(self, model: str, usage: dict[str, int]) -> float:
        p = self.price(model)
        inp = int(usage.get("input_tokens", 0) or 0)
        out = int(usage.get("output_tokens", 0) or 0)
        cr = int(usage.get("cache_read_input_tokens", 0) or 0)
        cw = int(usage.get("cache_creation_input_tokens", 0) or 0)
        in_price, out_price, scale = self._tier(p, inp + cr + cw)
        return (
            inp * in_price
            + out * out_price
            + cr * p.cache_read_price * scale
            + cw * p.cache_write_price * scale
        ) / 1e6

    def reservation(self, model: str, request: dict[str, Any]) -> float:
        """Worst case: every prompt token written to cache, and the full max_tokens out."""
        p = self.price(model)
        chars = len(json.dumps({k: request.get(k) for k in ("system", "messages", "tools")}, default=str))
        prompt_tokens = chars // 3 + 64
        in_price, out_price, scale = self._tier(p, prompt_tokens)
        write = max(in_price, p.cache_write_price * scale)
        return (prompt_tokens * write + int(request.get("max_tokens", 4096)) * out_price) / 1e6


DEFAULT_BOOK = PriceBook()
