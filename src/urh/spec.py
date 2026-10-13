"""Task specs: what a run is asked to do, and the checks that decide "done".

A spec is plain JSON. Steps are optional: with steps the manager is code (no
tokens); without them an Opus manager plans one step at a time from verified
state. Gate checks always come from the spec, never from the worker.

Example::

    {
      "goal": "Implement slugify() in slug.py",
      "constraints": ["Standard library only"],
      "seed_dir": "examples/slug/seed",
      "gate": {
        "hidden_dir": "examples/slug/hidden",
        "checks": [{"name": "tests", "cmd": ["python", "-m", "pytest", "-q", "_hidden"]}],
        "protected": ["_hidden/"]
      },
      "steps": [
        {"title": "slugify", "instructions": "Write slug.py with slugify(text) -> str ...",
         "files": ["slug.py"], "checks": ["tests"]}
      ],
      "budget_usd": 0.50
    }
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Check:
    name: str
    cmd: list[str]
    timeout: float = 120.0


@dataclass
class GateSpec:
    checks: list[Check] = field(default_factory=list)
    hidden_dir: str | None = None          # copied into the gate's checkout as ``_hidden``; never into the workspace
    protected: list[str] = field(default_factory=list)  # path prefixes the worker may not change


@dataclass
class StepSpec:
    title: str
    instructions: str
    files: list[str] = field(default_factory=list)   # the files this step is expected to write
    checks: list[str] | None = None                  # names of gate checks; None means all
    effects: list[dict[str, Any]] = field(default_factory=list)  # outward actions after the step verifies
    irreversible: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "instructions": self.instructions,
            "files": self.files,
            "checks": self.checks,
            "effects": self.effects,
            "irreversible": self.irreversible,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> StepSpec:
        return cls(
            title=d["title"],
            instructions=d["instructions"],
            files=list(d.get("files", [])),
            checks=d.get("checks"),
            effects=list(d.get("effects", [])),
            irreversible=bool(d.get("irreversible", False)),
        )


@dataclass
class TaskSpec:
    goal: str
    constraints: list[str] = field(default_factory=list)
    facts: list[str] = field(default_factory=list)
    seed_dir: str | None = None
    gate: GateSpec = field(default_factory=GateSpec)
    steps: list[StepSpec] | None = None
    budget_usd: float = 1.0
    max_repairs: int = 2
    max_worker_turns: int = 30
    max_steps: int = 20

    @classmethod
    def from_dict(cls, d: dict[str, Any], base_dir: str | None = None) -> TaskSpec:
        def _abs(p: str | None) -> str | None:
            if p is None or base_dir is None or os.path.isabs(p):
                return p
            return os.path.normpath(os.path.join(base_dir, p))

        g = d.get("gate", {})
        gate = GateSpec(
            checks=[Check(name=c["name"], cmd=list(c["cmd"]), timeout=float(c.get("timeout", 120)))
                    for c in g.get("checks", [])],
            hidden_dir=_abs(g.get("hidden_dir")),
            protected=list(g.get("protected", [])),
        )
        steps = d.get("steps")
        return cls(
            goal=d["goal"],
            constraints=list(d.get("constraints", [])),
            facts=list(d.get("facts", [])),
            seed_dir=_abs(d.get("seed_dir")),
            gate=gate,
            steps=None if steps is None else [StepSpec.from_dict(s) for s in steps],
            budget_usd=float(d.get("budget_usd", 1.0)),
            max_repairs=int(d.get("max_repairs", 2)),
            max_worker_turns=int(d.get("max_worker_turns", 30)),
            max_steps=int(d.get("max_steps", 20)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "goal": self.goal,
            "constraints": self.constraints,
            "facts": self.facts,
            "seed_dir": self.seed_dir,
            "gate": {
                "checks": [{"name": c.name, "cmd": c.cmd, "timeout": c.timeout} for c in self.gate.checks],
                "hidden_dir": self.gate.hidden_dir,
                "protected": self.gate.protected,
            },
            "steps": None if self.steps is None else [s.to_dict() for s in self.steps],
            "budget_usd": self.budget_usd,
            "max_repairs": self.max_repairs,
            "max_worker_turns": self.max_worker_turns,
            "max_steps": self.max_steps,
        }

    @classmethod
    def load(cls, path: str) -> TaskSpec:
        with open(path) as f:
            return cls.from_dict(json.load(f), base_dir=os.path.dirname(os.path.abspath(path)))
