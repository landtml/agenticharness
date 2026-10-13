"""Model gateway: the only door to model providers.

It holds every run to its pinned provider and models, reserves each call's
worst-case cost against the run's one global budget before the call, settles
the actual cost after, logs every call (tokens, cache hits, cost, latency, the
request and response by blob reference), and parks runs behind a circuit
breaker when the provider is down.

Only Anthropic is wired in. The coordinator/manager is Claude Opus 5.5 and the
workers are Claude Haiku 5.5.
"""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from .blobs import BlobStore
from .journal import Journal

MANAGER_MODEL = "claude-opus-5-5"
WORKER_MODEL = "claude-haiku-5-5"
PROVIDER = "anthropic"


@dataclass(frozen=True)
class Price:
    """USD per million tokens."""

    input: float
    output: float
    cache_read: float
    long_input: float | None = None     # price tier above ``long_threshold`` prompt tokens
    long_output: float | None = None
    long_threshold: int = 100_000

    @property
    def cache_write(self) -> float:      # 5-minute TTL write premium
        return self.input * 1.25


PRICES: dict[str, Price] = {
    "claude-opus-5-5": Price(input=4.00, output=20.00, cache_read=0.20),
    "claude-haiku-5-5": Price(input=0.10, output=0.50, cache_read=0.01, long_input=0.50, long_output=2.50),
    "claude-sonnet-5-5": Price(input=2.00, output=10.00, cache_read=0.20),
}


def cost_usd(model: str, usage: dict[str, int]) -> float:
    p = PRICES[model]
    inp = int(usage.get("input_tokens", 0) or 0)
    out = int(usage.get("output_tokens", 0) or 0)
    cr = int(usage.get("cache_read_input_tokens", 0) or 0)
    cw = int(usage.get("cache_creation_input_tokens", 0) or 0)
    prompt = inp + cr + cw
    in_price, out_price = p.input, p.output
    if p.long_input is not None and prompt > p.long_threshold:
        in_price, out_price = p.long_input, p.long_output or p.output
    scale = in_price / p.input
    return (inp * in_price + out * out_price + cr * p.cache_read * scale + cw * p.cache_write * scale) / 1e6


def estimate_reservation(model: str, request: dict[str, Any]) -> float:
    """Worst case: every prompt token uncached at the write premium, and the full max_tokens out."""
    p = PRICES[model]
    chars = len(json.dumps({k: request.get(k) for k in ("system", "messages", "tools")}, default=str))
    prompt_tokens = chars // 3 + 64
    in_price, out_price = p.input, p.output
    if p.long_input is not None and prompt_tokens > p.long_threshold:
        in_price, out_price = p.long_input, p.long_output or p.output
    return (prompt_tokens * in_price * 1.25 + int(request.get("max_tokens", 4096)) * out_price) / 1e6


@dataclass
class ProviderResponse:
    content: list[dict[str, Any]]
    stop_reason: str | None
    usage: dict[str, int]
    model: str


class Provider(Protocol):
    name: str

    def complete(self, request: dict[str, Any]) -> ProviderResponse: ...


class ProviderUnavailable(Exception):
    """Transient: connection error, 429, 5xx. Counts toward the circuit breaker."""


class ProviderDown(Exception):
    """Retries are spent or the breaker is open. The orchestrator parks the run."""


class AnthropicProvider:
    """Calls the Messages API through the official SDK."""

    name = PROVIDER

    def __init__(self, client: Any | None = None, timeout: float = 600.0):
        if client is None:
            import anthropic

            client = anthropic.Anthropic(max_retries=0, timeout=timeout)
        self.client = client

    def complete(self, request: dict[str, Any]) -> ProviderResponse:
        import anthropic

        try:
            resp = self.client.messages.create(**request)
        except (anthropic.APIConnectionError, anthropic.RateLimitError, anthropic.InternalServerError) as e:
            raise ProviderUnavailable(str(e)) from e
        except anthropic.APIStatusError as e:
            if e.status_code >= 500 or e.status_code in (408, 409, 529):
                raise ProviderUnavailable(str(e)) from e
            raise
        content = [b.model_dump(exclude_none=True) for b in resp.content]
        usage = resp.usage.model_dump(exclude_none=True) if resp.usage else {}
        return ProviderResponse(content=content, stop_reason=resp.stop_reason, usage=usage, model=resp.model)


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
                self.opened_at = None   # half-open: let one call through
                self.failures = self.threshold - 1
                return True
            return False

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
    role: str          # manager | worker | judge
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
    ):
        self.journal = journal
        self.blobs = blobs
        self.provider = provider
        self.retries = retries
        self.backoff_s = backoff_s
        self.breaker = breaker or CircuitBreaker()
        self.sleep = sleep

    @staticmethod
    def default_pins() -> dict[str, Any]:
        return {"provider": PROVIDER, "models": {"manager": MANAGER_MODEL, "worker": WORKER_MODEL, "judge": WORKER_MODEL}}

    def call(self, ctx: CallContext, pins: dict[str, Any], request: dict[str, Any]) -> ProviderResponse:
        if pins.get("provider") != self.provider.name:
            raise RuntimeError(f"run pinned to provider {pins.get('provider')!r}, gateway serves {self.provider.name!r}")
        model = pins["models"][ctx.role]
        request = {**request, "model": model}
        reservation = estimate_reservation(model, request)
        request_blob = self.blobs.put_json(request)
        call_id = self.journal.reserve(
            ctx.run_id,
            ctx.epoch,
            {
                "step_index": ctx.step_index, "attempt": ctx.attempt, "call_index": ctx.call_index,
                "role": ctx.role, "provider": self.provider.name, "model": model, "request_blob": request_blob,
            },
            reservation,
        )
        last_error: Exception | None = None
        for i in range(self.retries + 1):
            if not self.breaker.allow():
                last_error = ProviderDown("circuit breaker open")
                break
            t0 = time.monotonic()
            try:
                resp = self.provider.complete(request)
            except ProviderUnavailable as e:
                self.breaker.record(False)
                last_error = e
                if i < self.retries:
                    self.sleep(self.backoff_s * (2**i))
                continue
            except Exception as e:
                self.journal.settle(call_id, 0.0, {"error": repr(e)[:2000]}, status="error")
                raise
            self.breaker.record(True)
            latency = int((time.monotonic() - t0) * 1000)
            if resp.model and resp.model != model and not resp.model.startswith(model):
                # A silent substitution is a version change; do not accept it as the pinned model's work.
                self.journal.settle(call_id, cost_usd(model, resp.usage), {"error": f"model drift: {resp.model}"},
                                    status="error")
                raise ProviderDown(f"provider served {resp.model} for pinned {model}")
            cost = cost_usd(model, resp.usage)
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
                        {"content": resp.content, "stop_reason": resp.stop_reason, "usage": resp.usage, "model": resp.model}
                    ),
                },
            )
            return resp
        self.journal.settle(call_id, 0.0, {"error": repr(last_error)[:2000]}, status="error")
        raise ProviderDown(f"provider unavailable after {self.retries + 1} tries: {last_error}")
