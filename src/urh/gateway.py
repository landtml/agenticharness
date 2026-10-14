"""Model gateway: the only door to model providers.

It holds every run to its pinned provider and role-to-model mapping, reserves
each call's worst-case cost against the run's one global budget before the
call, settles the actual cost after, logs every call (tokens, cache hits, cost,
latency, the request and response by blob reference), and parks runs behind a
circuit breaker when the provider is down.

Nothing here is specific to one vendor. Providers are adapters behind one
interface (``urh.providers``); which model plays which role is configuration.
This repository develops and tests with Claude Opus 5.5 as manager and Claude
Haiku 5.5 as worker, which are only the defaults.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from .blobs import BlobStore
from .journal import Journal
from .pricing import DEFAULT_BOOK, DEFAULT_PRICES, Price, PriceBook
from .providers.anthropic import AnthropicProvider
from .providers.base import Provider, ProviderDown, ProviderResponse, ProviderUnavailable, RateLimited

__all__ = [
    "AnthropicProvider",
    "CallContext",
    "CircuitBreaker",
    "DEFAULT_MODELS",
    "ModelGateway",
    "PRICES",
    "Price",
    "Provider",
    "ProviderDown",
    "ProviderResponse",
    "ProviderUnavailable",
    "cost_usd",
    "estimate_reservation",
]

ROLES = ("manager", "planner", "worker", "judge", "escalation")
DEFAULT_MODELS: dict[str, str] = {
    "manager": "claude-opus-5-5",
    # writes plans and milestone expansions; replans go to the manager (see urh.routing)
    "planner": "claude-opus-5-5",
    "worker": "claude-haiku-5-5",
    "judge": "claude-haiku-5-5",
    # one stronger attempt when the worker's repairs are exhausted, before anything parks
    "escalation": "claude-opus-5-5",
}
MANAGER_MODEL = DEFAULT_MODELS["manager"]
WORKER_MODEL = DEFAULT_MODELS["worker"]
PRICES = DEFAULT_PRICES


def cost_usd(model: str, usage: dict[str, int]) -> float:
    return DEFAULT_BOOK.cost(model, usage)


def estimate_reservation(model: str, request: dict[str, Any]) -> float:
    return DEFAULT_BOOK.reservation(model, request)


@dataclass
class CircuitBreaker:
    threshold: int = 3
    cooldown_s: float = 60.0
    failures: int = 0
    opened_at: float | None = None
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def allow(self) -> bool:
        with self._lock:
            if self.opened_at is None:
                return True
            if time.monotonic() - self.opened_at >= self.cooldown_s:
                self.opened_at = None  # half-open: let one call through
                self.failures = self.threshold - 1
                return True
            return False

    def is_open(self) -> bool:
        """True while calls are refused; unlike ``allow`` it never moves the breaker to half-open."""
        with self._lock:
            return self.opened_at is not None and time.monotonic() - self.opened_at < self.cooldown_s

    def record(self, ok: bool) -> None:
        with self._lock:
            if ok:
                self.failures = 0
                self.opened_at = None
            else:
                self.failures += 1
                if self.failures >= self.threshold:
                    self.opened_at = time.monotonic()


@dataclass
class CallContext:
    run_id: str
    epoch: int
    step_index: int
    attempt: int
    role: str  # one of ROLES
    call_index: int


class ModelGateway:
    def __init__(
        self,
        journal: Journal,
        blobs: BlobStore,
        provider: Provider,
        retries: int = 3,
        backoff_s: float = 2.0,
        breaker: CircuitBreaker | None = None,
        sleep: Callable[[float], None] = time.sleep,
        prices: PriceBook | None = None,
        max_concurrent_calls: int | None = None,
        rate_limit_retries: int = 8,
        max_rate_wait_s: float = 120.0,
    ):
        self.journal = journal
        # one gate for every run in this process: parallel runs share the provider's rate limit
        self._slots = threading.BoundedSemaphore(max_concurrent_calls) if max_concurrent_calls else None
        self.rate_limit_retries = rate_limit_retries
        self.max_rate_wait_s = max_rate_wait_s
        self.blobs = blobs
        self.provider = provider
        self.retries = retries
        self.backoff_s = backoff_s
        self.breaker = breaker or CircuitBreaker()
        self.sleep = sleep
        self.prices = prices or DEFAULT_BOOK

    def pins_for(self, models: dict[str, str] | None = None) -> dict[str, Any]:
        """Pins recorded on a new run: this gateway's provider and a model for every role."""
        models = dict(models or {})
        # A role left out follows its natural sibling before the defaults, so a config that names
        # only vendor models never silently falls back to another vendor for judge or escalation.
        for role, sibling in (("judge", "worker"), ("escalation", "manager"), ("planner", "manager")):
            if role not in models and sibling in models:
                models[role] = models[sibling]
        chosen = {**DEFAULT_MODELS, **models}
        return {"provider": self.provider.name, "models": {r: chosen[r] for r in ROLES}}

    @staticmethod
    def default_pins() -> dict[str, Any]:
        return {"provider": "anthropic", "models": dict(DEFAULT_MODELS)}

    def _cost(self, model: str, resp: ProviderResponse) -> float:
        return resp.cost_usd if resp.cost_usd is not None else self.prices.cost(model, resp.usage)

    def call(self, ctx: CallContext, pins: dict[str, Any], request: dict[str, Any]) -> ProviderResponse:
        if pins.get("provider") != self.provider.name:
            raise RuntimeError(
                f"run pinned to provider {pins.get('provider')!r}, gateway serves {self.provider.name!r}"
            )
        model = pins["models"][ctx.role]
        request = {**request, "model": model}
        reservation = self.prices.reservation(model, request)
        request_blob = self.blobs.put_json(request)
        call_id = self.journal.reserve(
            ctx.run_id,
            ctx.epoch,
            {
                "step_index": ctx.step_index,
                "attempt": ctx.attempt,
                "call_index": ctx.call_index,
                "role": ctx.role,
                "provider": self.provider.name,
                "model": model,
                "request_blob": request_blob,
            },
            reservation,
        )
        last_error: Exception | None = None
        failures = limited = 0
        while failures <= self.retries:
            if not self.breaker.allow():
                last_error = ProviderDown("circuit breaker open")
                break
            t0 = time.monotonic()
            try:
                if self._slots is not None:
                    with self._slots:
                        resp = self.provider.complete(request)
                else:
                    resp = self.provider.complete(request)
            except RateLimited as e:
                # The provider is up; it wants us slower. Wait as told, without tripping the breaker.
                limited += 1
                last_error = e
                if limited > self.rate_limit_retries:
                    break
                wait = e.retry_after if e.retry_after is not None else self.backoff_s * (2 ** min(limited, 6))
                self.sleep(min(wait, self.max_rate_wait_s))
                continue
            except ProviderUnavailable as e:
                self.breaker.record(False)
                last_error = e
                failures += 1
                if failures <= self.retries:
                    self.sleep(self.backoff_s * (2 ** (failures - 1)))
                continue
            except Exception as e:
                self.journal.settle(call_id, 0.0, {"error": repr(e)[:2000]}, status="error")
                raise
            self.breaker.record(True)
            latency = int((time.monotonic() - t0) * 1000)
            if resp.model and resp.model != model and not resp.model.startswith(model):
                # A silent substitution is a version change; do not accept it as the pinned model's work.
                self.journal.settle(
                    call_id,
                    self._cost(model, resp),
                    {"error": f"model drift: {resp.model}"},
                    status="error",
                )
                raise ProviderDown(f"provider served {resp.model} for pinned {model}")
            cost = self._cost(model, resp)
            self.journal.settle(
                call_id,
                cost,
                {
                    "input_tokens": resp.usage.get("input_tokens"),
                    "output_tokens": resp.usage.get("output_tokens"),
                    "cache_read": resp.usage.get("cache_read_input_tokens"),
                    "cache_write": resp.usage.get("cache_creation_input_tokens"),
                    "latency_ms": latency,
                    "stop_reason": resp.stop_reason,
                    "response_blob": self.blobs.put_json(
                        {
                            "content": resp.content,
                            "stop_reason": resp.stop_reason,
                            "usage": resp.usage,
                            "model": resp.model,
                        }
                    ),
                },
            )
            return resp
        self.journal.settle(call_id, 0.0, {"error": repr(last_error)[:2000]}, status="error")
        raise ProviderDown(f"provider unavailable after {failures + limited} tries: {last_error}")
