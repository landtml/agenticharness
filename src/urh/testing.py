"""A deterministic stand-in for the Anthropic provider, for tests and offline demos.

A script maps a step (and optionally an attempt) to the worker's turns::

    {
      "steps": {
        "1":   [[{"write": "a.py", "content": "..."}], [{"finish": "done"}]],
        "2":   [[{"hang_once": "/tmp/marker"}, {"write": "b.py", "content": "..."}], [{"finish": "ok"}]],
        "2@2": [[{"write": "b.py", "content": "fixed"}], [{"finish": "repaired"}]]
      },
      "plan": [{"title": "...", "instructions": "...", "files": ["a.py"], "checks": []}, {"done": true}],
      "fail_calls": 0
    }

Each turn is a list of actions turned into tool calls. ``hang_once`` blocks
forever the first time it is reached (so a test can ``kill -9`` the process),
and is skipped once its marker file exists.
"""

from __future__ import annotations

import json
import os
import re
import time
from typing import Any

from .gateway import ProviderResponse, ProviderUnavailable

_STEP = re.compile(r"^STEP (\d+)", re.M)
_REPAIR = re.compile(r"REPAIR \(attempt (\d+)\)")


class ScriptedProvider:
    name = "anthropic"  # stands in for the pinned provider so runs can move between real and scripted

    def __init__(self, script: dict[str, Any]):
        self.script = script
        self.calls = 0
        self.fail_calls = int(script.get("fail_calls", 0))

    @classmethod
    def from_file(cls, path: str) -> ScriptedProvider:
        with open(path) as f:
            return cls(json.load(f))

    def complete(self, request: dict[str, Any]) -> ProviderResponse:
        self.calls += 1
        if self.fail_calls > 0:
            self.fail_calls -= 1
            raise ProviderUnavailable("scripted outage")
        usage = {
            "input_tokens": len(json.dumps(request.get("messages"), default=str)) // 4,
            "output_tokens": 40,
            "cache_read_input_tokens": 0,
            "cache_creation_input_tokens": 0,
        }
        if request.get("response_schema"):
            return self._plan(request, usage)
        messages = request["messages"]
        first = messages[0]["content"]
        step_no = _STEP.search(first).group(1)  # type: ignore[union-attr]
        rep = _REPAIR.search(first)
        key = f"{step_no}@{rep.group(1)}" if rep else step_no
        turns = self.script["steps"].get(key) or self.script["steps"].get(step_no) or []
        turn = sum(1 for m in messages if m["role"] == "assistant")
        if turn >= len(turns):
            return ProviderResponse(
                [{"type": "text", "text": "Nothing more to do."}], "end_turn", usage, request["model"]
            )
        content: list[dict[str, Any]] = []
        for n, action in enumerate(turns[turn]):
            tid = f"toolu_{self.calls}_{n}"
            if "hang_once" in action:
                marker = action["hang_once"]
                if not os.path.exists(marker):
                    with open(marker, "w") as f:
                        f.write(str(os.getpid()))
                    while True:  # wait here to be killed
                        time.sleep(1)
            elif "sleep" in action:
                time.sleep(float(action["sleep"]))
            elif "write" in action:
                content.append(
                    {
                        "type": "tool_use",
                        "id": tid,
                        "name": "write_file",
                        "input": {"path": action["write"], "content": action["content"]},
                    }
                )
            elif "bash" in action:
                content.append(
                    {"type": "tool_use", "id": tid, "name": "bash", "input": {"command": action["bash"]}}
                )
            elif "effect" in action:
                content.append(
                    {
                        "type": "tool_use",
                        "id": tid,
                        "name": "propose_effect",
                        "input": {
                            "kind": action["effect"],
                            "payload_json": json.dumps(action.get("payload", {})),
                        },
                    }
                )
            elif "finish" in action:
                content.append(
                    {"type": "tool_use", "id": tid, "name": "finish", "input": {"summary": action["finish"]}}
                )
            elif "text" in action:
                content.append({"type": "text", "text": action["text"]})
        stop = "tool_use" if any(b["type"] == "tool_use" for b in content) else "end_turn"
        return ProviderResponse(content, stop, usage, request["model"])

    def _plan(self, request: dict[str, Any], usage: dict[str, int]) -> ProviderResponse:
        text = request["messages"][0]["content"]
        m = re.search(r"Plan step (\d+)", text)
        idx = int(m.group(1)) - 1 if m else 0
        plan = self.script.get("plan", [])
        item = plan[idx] if idx < len(plan) else {"done": True}
        full = {"done": False, "title": "", "instructions": "", "files": [], "checks": [], **item}
        return ProviderResponse(
            [{"type": "text", "text": json.dumps(full)}], "end_turn", usage, request["model"]
        )
