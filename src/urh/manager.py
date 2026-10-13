"""Manager: picks the next step. Code for recurring task types, one Opus call per step for novel ones.

Either way the decision is journaled before the step runs (``step_plans``), so
a resume reuses it instead of asking again.
"""

from __future__ import annotations

import json
from typing import Any, Protocol

from .gateway import CallContext, ModelGateway
from .spec import StepSpec, TaskSpec

DONE = {"done": True}


class Manager(Protocol):
    source: str

    def next_step(
        self,
        *,
        run_id: str,
        epoch: int,
        pins: dict[str, Any],
        spec: TaskSpec,
        step_index: int,
        history: list[dict[str, Any]],
        files: list[str],
    ) -> dict[str, Any]: ...


class CodeManager:
    """The step list is written in the spec. No tokens."""

    source = "spec"

    def next_step(self, *, spec: TaskSpec, step_index: int, **_: Any) -> dict[str, Any]:
        assert spec.steps is not None
        if step_index >= len(spec.steps):
            return dict(DONE)
        return spec.steps[step_index].to_dict()


MANAGER_SYSTEM = """You are the manager of an automated build harness. You never write code yourself.
Each turn you choose the single next step for a worker model (a small, fast model with a shell and file tools).
You see only facts the harness verified: steps whose hidden checks passed, and the files in the verified tree.
Make each step small enough to finish in a few dozen tool calls, name the files it must write, and state the
expected behaviour and output shapes precisely, because hidden checks decide whether the step is done.
When the goal is met by the verified work, answer done=true."""

_SCHEMA = {
    "type": "object",
    "properties": {
        "done": {"type": "boolean"},
        "title": {"type": "string"},
        "instructions": {"type": "string"},
        "files": {"type": "array", "items": {"type": "string"}},
        "checks": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["done", "title", "instructions", "files", "checks"],
    "additionalProperties": False,
}


class LLMManager:
    """Claude Opus 5.5 plans one step at a time from verified state."""

    source = "manager"

    def __init__(self, gateway: ModelGateway, effort: str = "medium"):
        self.gateway = gateway
        self.effort = effort

    def next_step(
        self,
        *,
        run_id: str,
        epoch: int,
        pins: dict[str, Any],
        spec: TaskSpec,
        step_index: int,
        history: list[dict[str, Any]],
        files: list[str],
        **_: Any,
    ) -> dict[str, Any]:
        lines = [f"GOAL: {spec.goal}"]
        if spec.constraints:
            lines.append("CONSTRAINTS:\n" + "\n".join(f"- {c}" for c in spec.constraints))
        lines.append("GATE CHECKS AVAILABLE: " + ", ".join(c.name for c in spec.gate.checks))
        lines.append(
            "VERIFIED STEPS:\n"
            + ("\n".join(f"{h['step_index'] + 1}. {h['title']}" for h in history) or "(none)")
        )
        lines.append("FILES IN VERIFIED TREE:\n" + ("\n".join(files[:300]) or "(empty)"))
        lines.append(f"Plan step {step_index + 1}. Use [] for checks to run every gate check.")
        ctx = CallContext(run_id, epoch, step_index, 0, "manager", 0)
        resp = self.gateway.call(
            ctx,
            pins,
            {
                "max_tokens": 8000,
                "system": [{"type": "text", "text": MANAGER_SYSTEM, "cache_control": {"type": "ephemeral"}}],
                "messages": [{"role": "user", "content": "\n\n".join(lines)}],
                "effort": self.effort,
                "response_schema": _SCHEMA,
            },
        )
        text = "".join(b.get("text", "") for b in resp.content if b.get("type") == "text")
        data = json.loads(text)
        if data.get("done"):
            return dict(DONE)
        return StepSpec(
            title=data["title"],
            instructions=data["instructions"],
            files=list(data.get("files", [])),
            checks=list(data["checks"]) or None,
        ).to_dict()
