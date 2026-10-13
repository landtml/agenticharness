"""Worker: Claude Haiku 5.5 in a fresh context, one step, a small action space."""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from . import sandbox
from .gateway import CallContext, ModelGateway

MAX_TOOL_OUTPUT = 8000
WORKER_MAX_TOKENS = 16000

TOOLS: list[dict[str, Any]] = [
    {
        "name": "bash",
        "description": "Run a shell command in the project folder (no network). Returns exit code, stdout and stderr.",
        "input_schema": {
            "type": "object",
            "properties": {"command": {"type": "string"}},
            "required": ["command"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "name": "read_file",
        "description": "Read a text file from the project folder.",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "name": "write_file",
        "description": "Create or overwrite a text file in the project folder.",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
            "required": ["path", "content"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "name": "list_files",
        "description": "List files under a folder of the project (default: the whole project).",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "name": "propose_effect",
        "description": "Queue an outward action (message, webhook, deploy). It fires once, only after this step verifies.",
        "input_schema": {
            "type": "object",
            "properties": {"kind": {"type": "string"}, "payload_json": {"type": "string"}},
            "required": ["kind", "payload_json"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "name": "finish",
        "description": "Declare the step's work complete. The hidden checks then decide.",
        "input_schema": {
            "type": "object",
            "properties": {"summary": {"type": "string"}},
            "required": ["summary"],
            "additionalProperties": False,
        },
        "strict": True,
    },
]


@dataclass
class WorkerOutcome:
    finished: bool
    summary: str
    turns: int
    stop_reason: str | None
    proposed_effects: int = 0
    notes: list[str] = field(default_factory=list)


class PathEscape(ValueError):
    pass


class Workspace:
    """Tool implementations confined to one folder. Real paths never reach the model."""

    def __init__(self, root: str, command_timeout: float = 60.0):
        self.root = os.path.realpath(root)
        self.command_timeout = command_timeout

    def _resolve(self, rel: str) -> str:
        rel = rel.strip() or "."
        if rel.startswith("/work"):
            rel = rel[len("/work") :].lstrip("/") or "."
        path = os.path.realpath(os.path.join(self.root, rel))
        if path != self.root and not path.startswith(self.root + os.sep):
            raise PathEscape(f"path is outside the project folder: {rel}")
        return path

    def _hide(self, text: str) -> str:
        return text.replace(self.root, "/work")

    def bash(self, command: str) -> str:
        r = sandbox.run(
            command, cwd=self.root, timeout=self.command_timeout, env=sandbox.scrubbed_env(self.root)
        )
        out = f"exit={r.returncode}{' (timed out)' if r.timed_out else ''}\n--- stdout\n{r.stdout}\n--- stderr\n{r.stderr}"
        return self._hide(out)[:MAX_TOOL_OUTPUT]

    def read_file(self, path: str) -> str:
        p = self._resolve(path)
        if not os.path.isfile(p):
            return f"no such file: {path}"
        with open(p, errors="replace") as f:
            return self._hide(f.read())[:MAX_TOOL_OUTPUT]

    def write_file(self, path: str, content: str) -> str:
        p = self._resolve(path)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w") as f:
            f.write(content)
        return f"wrote {os.path.relpath(p, self.root)} ({len(content)} chars)"

    def list_files(self, path: str = ".") -> str:
        base = self._resolve(path)
        out = []
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = sorted(d for d in dirnames if not d.startswith(".") and d != "__pycache__")
            for fn in sorted(filenames):
                out.append(os.path.relpath(os.path.join(dirpath, fn), self.root))
            if len(out) > 500:
                break
        return "\n".join(out) or "(empty)"


ProposeFn = Callable[[int, str, dict[str, Any]], str]


class Worker:
    def __init__(self, gateway: ModelGateway, effort: str = "medium"):
        self.gateway = gateway
        self.effort = effort

    def run_step(
        self,
        *,
        run_id: str,
        epoch: int,
        step_index: int,
        attempt: int,
        pins: dict[str, Any],
        system: list[dict[str, Any]],
        first_message: str,
        workspace: Workspace,
        propose: ProposeFn,
        max_turns: int,
    ) -> WorkerOutcome:
        messages: list[dict[str, Any]] = [{"role": "user", "content": first_message}]
        effects = 0
        stop: str | None = None
        for turn in range(max_turns):
            ctx = CallContext(run_id, epoch, step_index, attempt, "worker", turn)
            resp = self.gateway.call(
                ctx,
                pins,
                {
                    "max_tokens": WORKER_MAX_TOKENS,
                    "system": system,
                    "tools": TOOLS,
                    "messages": messages,
                    "output_config": {"effort": self.effort},
                },
            )
            stop = resp.stop_reason
            messages.append({"role": "assistant", "content": resp.content})
            tool_uses = [b for b in resp.content if b.get("type") == "tool_use"]
            results: list[dict[str, Any]] = []
            finished: str | None = None
            for tu in tool_uses:
                name, args = tu.get("name"), tu.get("input") or {}
                try:
                    if name == "finish":
                        finished = str(args.get("summary", ""))[:500]
                        text = "recorded; the hidden checks decide next"
                    elif name == "propose_effect":
                        payload = json.loads(args.get("payload_json") or "{}")
                        if not isinstance(payload, dict):
                            raise ValueError("payload_json must encode an object")
                        propose(effects, str(args["kind"]), payload)
                        effects += 1
                        text = "queued; it fires once, after this step verifies"
                    elif name == "bash":
                        text = workspace.bash(str(args["command"]))
                    elif name == "read_file":
                        text = workspace.read_file(str(args["path"]))
                    elif name == "write_file":
                        text = workspace.write_file(str(args["path"]), str(args["content"]))
                    elif name == "list_files":
                        text = workspace.list_files(str(args.get("path", ".")))
                    else:
                        raise ValueError(f"unknown tool {name}")
                    results.append({"type": "tool_result", "tool_use_id": tu["id"], "content": text})
                except (KeyError, ValueError, OSError, json.JSONDecodeError) as e:
                    results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": tu["id"],
                            "is_error": True,
                            "content": f"error: {e}"[:1000],
                        }
                    )
            if finished is not None:
                return WorkerOutcome(True, finished, turn + 1, stop, effects)
            if stop == "max_tokens":
                # Cut-off reply: answer any complete tool calls and ask it to carry on, don't quit.
                results.append(
                    {
                        "type": "text",
                        "text": "Your last reply was cut off. Continue from where you stopped, more briefly.",
                    }
                )
                messages.append({"role": "user", "content": results})
                continue
            if stop == "pause_turn":
                continue
            if stop in ("end_turn", "stop_sequence", "refusal") and not tool_uses:
                return WorkerOutcome(False, "", turn + 1, stop, effects)
            if results:
                messages.append({"role": "user", "content": results})
        return WorkerOutcome(False, "", max_turns, stop, effects, ["turn limit reached"])
