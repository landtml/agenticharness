"""Gate audit: run a step's gate against a corpus of broken artifacts and report its false-accept rate.

The recipe's weakest leg is the gate: every "verified" count inherits its
errors. This measures them. A corpus is a folder of mutants, each a folder of
files laid over the seed (for example ``mutants/no_strip/slug.py``), plus an
optional ``reference`` folder that the gate must accept.

Usage: ``python -m urh.bench.gate_audit examples/slug/spec.json --step 2 --mutants examples/slug/mutants
--reference examples/slug/reference``
"""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import sys
import tempfile
from collections.abc import Callable
from typing import Any

from ..checkpoint import GitCheckpoint
from ..gate import ScriptGate
from ..spec import StepSpec, TaskSpec


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def _candidate(ckpt: GitCheckpoint, epoch: int, root: str, overlay: str) -> str:
    ws = ckpt.prepare_workspace(epoch, root)
    for dirpath, _, files in os.walk(overlay):
        for fn in files:
            src = os.path.join(dirpath, fn)
            dst = os.path.join(ws, os.path.relpath(src, overlay))
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy(src, dst)
    _, commit = ckpt.snapshot(epoch, root, f"audit {os.path.basename(overlay)}")
    return commit


Evaluate = Callable[[GitCheckpoint, str, str, StepSpec], str]


def audit(
    spec: TaskSpec,
    step_number: int,
    mutants_dir: str,
    reference_dir: str | None = None,
    evaluate: Evaluate | None = None,
) -> dict[str, Any]:
    """``evaluate(ckpt, parent, candidate, step) -> status`` defaults to the spec's script gate."""
    assert spec.steps is not None
    step = spec.steps[step_number - 1]
    if evaluate is None:
        gate = ScriptGate(spec.gate)

        def evaluate(ckpt: GitCheckpoint, parent: str, candidate: str, step: StepSpec) -> str:
            return gate.evaluate(ckpt, parent, candidate, step).status

    verdicts: dict[str, str] = {}
    names = sorted(d for d in os.listdir(mutants_dir) if os.path.isdir(os.path.join(mutants_dir, d)))
    with tempfile.TemporaryDirectory(prefix="urh-audit-") as tmp:
        ckpt = GitCheckpoint(tmp)
        root = ckpt.init(spec.seed_dir)
        epoch = 1
        reference_ok = None
        if reference_dir:
            verdicts["reference"] = evaluate(ckpt, root, _candidate(ckpt, epoch, root, reference_dir), step)
            reference_ok = verdicts["reference"] == "pass"
            epoch += 1
        accepted = []
        for name in names:
            commit = _candidate(ckpt, epoch, root, os.path.join(mutants_dir, name))
            epoch += 1
            verdicts[name] = evaluate(ckpt, root, commit, step)
            if verdicts[name] == "pass":
                accepted.append(name)
    n, k = len(names), len(accepted)
    lo, hi = wilson(k, n)
    return {
        "step": step.title,
        "checks": step.checks,
        "reference_accepted": reference_ok,
        "mutants": n,
        "accepted": accepted,
        "false_accept_rate": round(k / n, 4) if n else 0.0,
        "interval95": [round(lo, 4), round(hi, 4)],
        "verdicts": verdicts,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m urh.bench.gate_audit")
    p.add_argument("spec")
    p.add_argument("--step", type=int, required=True, help="1-based step number")
    p.add_argument("--mutants", required=True)
    p.add_argument("--reference")
    args = p.parse_args(argv)
    spec = TaskSpec.load(args.spec)
    for check in spec.gate.checks:
        if check.cmd and check.cmd[0] == "python":
            check.cmd[0] = sys.executable
    print(json.dumps(audit(spec, args.step, args.mutants, args.reference), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
