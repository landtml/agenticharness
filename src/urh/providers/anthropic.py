"""Anthropic Messages API adapter (official SDK)."""

from __future__ import annotations

from typing import Any

from .base import ProviderResponse, ProviderUnavailable


def to_messages_api(request: dict[str, Any]) -> dict[str, Any]:
    """Canonical request -> Messages API kwargs."""
    out = {k: v for k, v in request.items() if k not in ("effort", "response_schema")}
    output_config: dict[str, Any] = {}
    if request.get("effort"):
        output_config["effort"] = request["effort"]
    if request.get("response_schema"):
        output_config["format"] = {"type": "json_schema", "schema": request["response_schema"]}
    if output_config:
        out["output_config"] = output_config
    return out


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, client: Any | None = None, timeout: float = 600.0):
        if client is None:
            import anthropic

            client = anthropic.Anthropic(max_retries=0, timeout=timeout)
        self.client = client

    def complete(self, request: dict[str, Any]) -> ProviderResponse:
        import anthropic

        try:
            resp = self.client.messages.create(**to_messages_api(request))
        except (anthropic.APIConnectionError, anthropic.RateLimitError, anthropic.InternalServerError) as e:
            raise ProviderUnavailable(str(e)) from e
        except anthropic.APIStatusError as e:
            if e.status_code >= 500 or e.status_code in (408, 409, 529):
                raise ProviderUnavailable(str(e)) from e
            raise
        content = [b.model_dump(exclude_none=True) for b in resp.content]
        usage = resp.usage.model_dump(exclude_none=True) if resp.usage else {}
        return ProviderResponse(content=content, stop_reason=resp.stop_reason, usage=usage, model=resp.model)
