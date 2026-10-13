"""The provider interface every model adapter implements."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass
class ProviderResponse:
    content: list[dict[str, Any]]
    stop_reason: str | None
    usage: dict[str, int]  # input_tokens, output_tokens, cache_read_input_tokens, cache_creation_input_tokens
    model: str
    cost_usd: float | None = (
        None  # set when the provider reports what it billed; otherwise the price book decides
    )


class Provider(Protocol):
    name: str

    def complete(self, request: dict[str, Any]) -> ProviderResponse: ...


class ProviderUnavailable(Exception):
    """Transient: connection error, 429, 5xx. Counts toward the circuit breaker."""


class ProviderDown(Exception):
    """Retries are spent or the breaker is open. The orchestrator parks the run."""
