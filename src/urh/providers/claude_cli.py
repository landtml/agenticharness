"""Claude Code CLI adapter: reach Claude models through a signed-in ``claude`` CLI, no API key.

Each canonical request becomes one headless ``claude -p`` call with the CLI's own tools
switched off, no user settings and no MCP servers, so the CLI is only a transport:

- ``response_schema`` maps to ``--json-schema``; ``effort`` maps to ``--effort``.
- Client tools are emulated. The CLI cannot hand native tool calls back to the caller, so
  the tool catalogue goes into the system prompt and the model answers with a JSON object
  ``{"text": ..., "tool_calls": [{"name": ..., "input_json": ...}]}`` under a JSON schema.
  The adapter turns that into canonical ``tool_use`` blocks, and renders earlier tool calls
  and results back into the transcript on the next turn. The worker's loop, tools, sandbox
  and gates are the same as with any other provider.
- The CLI reports what each call billed, so ``cost_usd`` comes from the CLI, not the price book.

This is one provider among several; nothing in the harness depends on it.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from typing import Any

from .base import ProviderResponse, ProviderUnavailable

_STOP = {"end_turn": "end_turn", "max_tokens": "max_tokens", "refusal": "refusal"}

TOOL_PROTOCOL = """

TOOLS
You act only through these tools. Answer every turn with one JSON object:
{"text": "<optional short note>", "tool_calls": [{"name": "<tool>", "input_json": "<JSON object as a string>"}]}
List several calls to run them in order. An empty tool_calls list ends your turn.
Earlier calls and their results appear in the transcript as TOOL CALL and TOOL RESULT entries.

"""


def _text(content: Any) -> str:
    if isinstance(content, str):
        return content
    return "\n".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")


def render_tools(tools: list[dict[str, Any]]) -> str:
    lines = []
    for t in tools:
        schema = json.dumps(t.get("input_schema", {}), sort_keys=True)
        lines.append(f"- {t['name']}: {t.get('description', '')}\n  input schema: {schema}")
    return TOOL_PROTOCOL + "\n".join(lines)


def render_transcript(messages: list[dict[str, Any]]) -> str:
    """Canonical messages -> one prompt. Append-only: earlier turns render identically every time."""
    if len(messages) == 1 and isinstance(messages[0]["content"], str):
        return messages[0]["content"]
    out: list[str] = []
    for m in messages:
        content = m["content"]
        if isinstance(content, str):
            out.append(f"{m['role'].upper()}:\n{content}")
            continue
        for b in content:
            kind = b.get("type")
            if kind == "text" and b.get("text"):
                out.append(f"{m['role'].upper()}:\n{b['text']}")
            elif kind == "tool_use":
                out.append(f"TOOL CALL [{b['id']}] {b['name']} {json.dumps(b.get('input', {}), sort_keys=True)}")
            elif kind == "tool_result":
                body = b.get("content")
                body = body if isinstance(body, str) else _text(body or [])
                flag = " (error)" if b.get("is_error") else ""
                out.append(f"TOOL RESULT [{b['tool_use_id']}]{flag}:\n{body}")
    out.append("Continue: answer with the JSON object.")
    return "\n\n".join(out)


def tool_schema(tools: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "text": {"type": "string"},
            "tool_calls": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "enum": [t["name"] for t in tools]},
                        "input_json": {"type": "string"},
                    },
                    "required": ["name", "input_json"],
                },
            },
        },
        "required": ["text", "tool_calls"],
    }


def parse_tool_answer(answer: Any, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(answer, dict):
        return [{"type": "text", "text": str(answer)}]
    blocks: list[dict[str, Any]] = []
    if answer.get("text"):
        blocks.append({"type": "text", "text": str(answer["text"])})
    turn = sum(1 for m in messages if m["role"] == "assistant")
    seed = hashlib.sha1(json.dumps(messages[:1], sort_keys=True, default=str).encode()).hexdigest()[:8]
    for n, call in enumerate(answer.get("tool_calls") or []):
        raw = call.get("input_json", "{}")
        try:
            args = json.loads(raw) if isinstance(raw, str) else dict(raw)
            if not isinstance(args, dict):
                raise ValueError
        except (ValueError, TypeError):
            args = {"_unparsed": str(raw)[:2000]}  # the tool rejects it and the model sees why
        blocks.append({"type": "tool_use", "id": f"toolu_cli_{seed}_{turn}_{n}", "name": call.get("name", ""),
                       "input": args})
    return blocks


class ClaudeCliProvider:
    name = "claude-cli"

    def __init__(self, binary: str | None = None, timeout: float = 900.0):
        self.binary = binary or os.environ.get("URH_CLAUDE_BIN", "claude")
        self.timeout = timeout

    def build_command(self, request: dict[str, Any]) -> tuple[list[str], str]:
        tools = request.get("tools") or []
        system = _text(request.get("system") or "")
        schema = request.get("response_schema")
        if tools:
            system += render_tools(tools)
            schema = tool_schema(tools)
        cmd = [self.binary, "-p", "--model", request["model"], "--system-prompt", system, "--tools", "",
               "--setting-sources", "", "--strict-mcp-config", "--no-session-persistence",
               "--output-format", "json"]
        if request.get("effort"):
            cmd += ["--effort", str(request["effort"])]
        if schema is not None:
            cmd += ["--json-schema", json.dumps(schema)]
        return cmd, render_transcript(request["messages"])

    def complete(self, request: dict[str, Any]) -> ProviderResponse:
        cmd, prompt = self.build_command(request)
        try:
            proc = subprocess.run(cmd, input=prompt, capture_output=True, text=True, timeout=self.timeout)
        except subprocess.TimeoutExpired as e:
            raise ProviderUnavailable(f"claude CLI timed out after {self.timeout:.0f}s") from e
        except OSError as e:
            raise ProviderUnavailable(f"claude CLI could not start: {e}") from e
        try:
            d = json.loads(proc.stdout)
        except json.JSONDecodeError as e:
            raise ProviderUnavailable(f"claude CLI exit {proc.returncode}: {(proc.stderr or proc.stdout)[-500:]}") from e
        status = d.get("api_error_status")
        if d.get("is_error") and (not status or int(status) >= 429):
            raise ProviderUnavailable(f"claude CLI error ({status}): {str(d.get('result'))[:300]}")
        if d.get("is_error"):
            raise RuntimeError(f"claude CLI rejected the request ({status}): {str(d.get('result'))[:300]}")
        structured = d.get("structured_output")
        if request.get("tools"):
            content = parse_tool_answer(structured, request["messages"])
            stop = "tool_use" if any(b["type"] == "tool_use" for b in content) else "end_turn"
        else:
            text = json.dumps(structured) if structured is not None else (d.get("result") or "")
            content = [{"type": "text", "text": text}]
            stop = _STOP.get(str(d.get("stop_reason")), "end_turn")
        usage = d.get("usage") or {}
        return ProviderResponse(
            content=content,
            stop_reason=stop,
            usage={k: int(usage.get(k) or 0) for k in ("input_tokens", "output_tokens", "cache_read_input_tokens",
                                                         "cache_creation_input_tokens")},
            model=request["model"],
            cost_usd=float(d.get("total_cost_usd") or 0.0),
        )
