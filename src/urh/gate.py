"""Gate: decides "done" by reading the artifact, never the worker's report.

Checks run on a throwaway export of the candidate commit, with the hidden
tests copied in as ``_hidden``. The worker cannot write to either. Scripts
decide first; if no script applies, the verdict is ``unsure`` and the run
parks rather than guessing.
"""

from __future__ import annotations

import os
import re
import shutil
import tempfile
from dataclasses import asdict, dataclass, field
from typing import Any

from . import sandbox
from .checkpoint import GitCheckpoint
from .spec import Check, GateSpec, StepSpec

MAX_FAILURES = 10
MAX_FAILURE_LEN = 160
_PYTEST_FAILED = re.compile(r"^(?:FAILED|ERROR)\s+(\S+)", re.M)


@dataclass
class CheckResult:
    name: str
    passed: bool
    returncode: int
    timed_out: bool
    failures: list[str] = field(default_factory=list)


@dataclass
class Verdict:
    status: str  # pass | fail | unsure
    summary: str
    checks: list[CheckResult] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _sanitize(name: str) -> str:
    """Keep only file-name-level detail so failures never leak real paths."""
    name = name.replace("\\", "/")
    parts = name.split("::")
    parts[0] = os.path.basename(parts[0])
    out = "::".join(parts)
    return out[:MAX_FAILURE_LEN]


def extract_failures(stdout: str, stderr: str) -> list[str]:
    names = [_sanitize(m) for m in _PYTEST_FAILED.findall(stdout)]
    if not names:
        tail = (stderr or stdout).strip().splitlines()[-1:] or ["check failed"]
        names = [_sanitize(tail[0])]
    seen: list[str] = []
    for n in names:
        if n not in seen:
            seen.append(n)
    return seen[:MAX_FAILURES]


class ScriptGate:
    def __init__(self, spec: GateSpec):
        self.spec = spec

    def _selected(self, step: StepSpec) -> list[Any]:
        if step.checks is None:
            chosen = list(self.spec.checks)
        else:
            wanted = set(step.checks)
            chosen = [c for c in self.spec.checks if c.name in wanted]
        # Planner-authored checks run alongside the spec's; the worker can never write either.
        chosen += [
            Check(f"plan{n + 1}", ["/bin/bash", "-c", cmd])
            for n, cmd in enumerate(step.plan_checks)
            if cmd.strip()
        ]
        return chosen

    def evaluate(self, ckpt: GitCheckpoint, parent: str, candidate: str, step: StepSpec) -> Verdict:
        changed = ckpt.changed_paths(parent, candidate)
        touched = [
            p for p in changed for prot in self.spec.protected if p == prot.rstrip("/") or p.startswith(prot)
        ]
        if touched or any(p == "_hidden" or p.startswith("_hidden/") for p in changed):
            return Verdict(
                "fail",
                "the step changed protected paths",
                failures=[_sanitize(p) for p in touched][:MAX_FAILURES] or ["_hidden"],
            )
        checks = self._selected(step)
        with tempfile.TemporaryDirectory(prefix="urh-gate-") as tmp:
            tree = os.path.join(tmp, "tree")
            ckpt.export(candidate, tree)
            missing = [f for f in step.files if not os.path.exists(os.path.join(tree, f))]
            if missing:
                return Verdict(
                    "fail",
                    "expected files are missing",
                    failures=[f"missing file: {_sanitize(m)}" for m in missing],
                )
            if not checks:
                return Verdict("unsure", "no script check applies to this step")
            if self.spec.hidden_dir:
                shutil.copytree(self.spec.hidden_dir, os.path.join(tree, "_hidden"), dirs_exist_ok=True)
            results: list[CheckResult] = []
            for check in checks:
                r = sandbox.run(check.cmd, cwd=tree, timeout=check.timeout, env=sandbox.scrubbed_env(tmp))
                passed = r.returncode == 0 and not r.timed_out
                failures = (
                    [] if passed else (["timed out"] if r.timed_out else extract_failures(r.stdout, r.stderr))
                )
                results.append(CheckResult(check.name, passed, r.returncode, r.timed_out, failures))
        failed = [c for c in results if not c.passed]
        if not failed:
            return Verdict("pass", f"{len(results)} check(s) passed", checks=results)
        flat = [f"{c.name}: {f}" for c in failed for f in c.failures][:MAX_FAILURES]
        return Verdict(
            "fail", f"{len(failed)} of {len(results)} check(s) failed", checks=results, failures=flat
        )


def audit_gate(
    gate: ScriptGate,
    ckpt: GitCheckpoint,
    parent: str,
    mutants: dict[str, str],
    step: StepSpec,
    snapshot_dir: Any,
) -> dict[str, Any]:
    """Run the gate against a corpus of broken artifacts and report its false-accept rate.

    ``mutants`` maps a mutant name to a directory holding a full broken tree.
    ``snapshot_dir(path) -> commit`` turns a directory into a candidate commit.
    """
    accepted = []
    for name, path in sorted(mutants.items()):
        commit = snapshot_dir(path)
        if gate.evaluate(ckpt, parent, commit, step).status == "pass":
            accepted.append(name)
    n = len(mutants)
    return {"mutants": n, "accepted": accepted, "false_accept_rate": (len(accepted) / n) if n else 0.0}
