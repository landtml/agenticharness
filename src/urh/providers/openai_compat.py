"""OpenAI-compatible chat-completions adapter (OpenAI, OpenRouter, vLLM, Ollama, ...).

Not used by this repository's tests against real endpoints; it exists so the
finished harness can run on any model. Translation is pure and unit-tested.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

from .base import ProviderResponse, ProviderUnavailable, RateLimited, parse_retry_after

_STOP = {"stop": "end_turn", "tool_calls": "tool_use", "length": "max_tokens", "content_filter": "refusal"}


def _text_of(content: Any) -> str:
    if isinstance(content, str):
        return content
    return "".join(b.get("text", "") for b in content if b.get("type") == "text")


def to_chat_completions(request: dict[str, Any]) -> dict[str, Any]:
    """Canonical request -> chat-completions body."""
    msgs: list[dict[str, Any]] = []
    system = request.get("system")
    if system:
        msgs.append(
            {"role": "system", "content": _text_of(system) if not isinstance(system, str) else system}
        )
    for m in request["messages"]:
        content = m["content"]
        if isinstance(content, str):
            msgs.append({"role": m["role"], "content": content})
            continue
        if m["role"] == "assistant":
            calls = [
                {
                    "id": b["id"],
                    "type": "function",
                    "function": {"name": b["name"], "arguments": json.dumps(b.get("input", {}))},
                }
                for b in content
                if b.get("type") == "tool_use"
            ]
            entry: dict[str, Any] = {"role": "assistant", "content": _text_of(content) or None}
            if calls:
                entry["tool_calls"] = calls
            msgs.append(entry)
        else:
            text_parts = []
            for b in content:
                if b.get("type") == "tool_result":
                    body = b.get("content", "")
                    body = body if isinstance(body, str) else _text_of(body)
                    if b.get("is_error"):
                        body = f"ERROR: {body}"
                    msgs.append({"role": "tool", "tool_call_id": b["tool_use_id"], "content": body})
                elif b.get("type") == "text":
                    text_parts.append(b["text"])
            if text_parts:
                msgs.append({"role": "user", "content": "\n".join(text_parts)})
    body: dict[str, Any] = {
        "model": request["model"],
        "messages": msgs,
        "max_tokens": request.get("max_tokens", 4096),
    }
    if request.get("tools"):
        body["tools"] = [
            {
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "parameters": t["input_schema"],
                },
            }
            for t in request["tools"]
        ]
    if request.get("response_schema"):
        body["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": "response", "schema": request["response_schema"], "strict": True},
        }
    if request.get("effort"):
        body["reasoning_effort"] = request["effort"]
    return body


def from_chat_completions(data: dict[str, Any]) -> ProviderResponse:
    choice = data["choices"][0]
    msg = choice.get("message", {})
    content: list[dict[str, Any]] = []
    if msg.get("content"):
        content.append({"type": "text", "text": msg["content"]})
    for call in msg.get("tool_calls") or []:
        fn = call.get("function", {})
        try:
            args = json.loads(fn.get("arguments") or "{}")
        except json.JSONDecodeError:
            args = {"_unparsed": fn.get("arguments")}
        content.append({"type": "tool_use", "id": call["id"], "name": fn.get("name"), "input": args})
    u = data.get("usage") or {}
    cached = (u.get("prompt_tokens_details") or {}).get("cached_tokens", 0) or 0
    usage = {
        "input_tokens": max(0, int(u.get("prompt_tokens", 0)) - int(cached)),
        "output_tokens": int(u.get("completion_tokens", 0)),
        "cache_read_input_tokens": int(cached),
        "cache_creation_input_tokens": 0,
    }
    stop = _STOP.get(choice.get("finish_reason") or "", "end_turn")
    if any(b["type"] == "tool_use" for b in content):
        stop = "tool_use"
    cost = u.get("cost")  # OpenRouter reports the billed cost when usage accounting is on
    return ProviderResponse(
        content, stop, usage, data.get("model", ""), float(cost) if cost is not None else None
    )


class OpenAICompatibleProvider:
    def __init__(
        self,
        base_url: str,
        api_key_env: str = "OPENAI_API_KEY",
        name: str = "openai-compatible",
        timeout: float = 600.0,
        extra_headers: dict[str, str] | None = None,
    ):
        self.name = name
        self.base_url = base_url.rstrip("/")
        self.api_key_env = api_key_env
        self.timeout = timeout
        self.extra_headers = extra_headers or {}

    def complete(self, request: dict[str, Any]) -> ProviderResponse:
        body = json.dumps(to_chat_completions(request)).encode()
        headers = {"Content-Type": "application/json", **self.extra_headers}
        key = os.environ.get(self.api_key_env)
        if key:
            headers["Authorization"] = f"Bearer {key}"
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions", data=body, headers=headers, method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:  # noqa: S310 (configured endpoint)
                return from_chat_completions(json.loads(resp.read()))
        except urllib.error.HTTPError as e:
            if e.code == 429:
                raise RateLimited("HTTP 429", parse_retry_after(e.headers.get("retry-after"))) from e
            if e.code >= 500 or e.code in (408, 409):
                raise ProviderUnavailable(f"HTTP {e.code}") from e
            raise
        except (urllib.error.URLError, TimeoutError) as e:
            raise ProviderUnavailable(str(e)) from e
