"""Model providers. The harness speaks one canonical request format; each adapter translates.

Canonical request (what the worker, manager and judge build)::

    {
      "model": "<set by the gateway from the run's pins>",
      "max_tokens": 16000,
      "system": [{"type": "text", "text": "...", "cache_control": {...}}],   # cache_control is a hint
      "messages": [{"role": "user" | "assistant", "content": str | [block, ...]}],
      "tools": [{"name", "description", "input_schema"}],                    # optional
      "effort": "low" | "medium" | "high",                                   # optional hint
      "response_schema": {...JSON schema...},                                # optional structured output
    }

Content blocks are ``text``, ``tool_use`` ({id, name, input}) and ``tool_result``
({tool_use_id, content, is_error}). Adapters may add opaque blocks of their own
(for example Anthropic ``thinking`` blocks); the harness passes them back
unchanged and never interprets them.

Canonical response: :class:`ProviderResponse` with the same block types and a
``stop_reason`` of ``end_turn``, ``tool_use``, ``max_tokens``, ``refusal`` or
``pause_turn``.
"""

from .base import Provider, ProviderDown, ProviderResponse, ProviderUnavailable

__all__ = ["Provider", "ProviderDown", "ProviderResponse", "ProviderUnavailable"]
