"""Judge audit: the model judge's false-accept rate on the same mutant corpora as the script gate.

The judge decides steps no script check covers. If it is lenient it turns parks
into wrong finishes, the worse failure, so it gets the same audit as the gate:
each mutant goes to the judge alone (as if no script applied), and the
reference must be accepted. ``unsure`` counts as not accepted.

Usage: ``python -m urh.bench.judge_audit examples/slug/spec.json --step 2 --mutants examples/slug/mutants
--reference examples/slug/reference --provider claude-cli [--model claude-haiku-5-5]``
"""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from typing import Any

from ..checkpoint import GitCheckpoint
from ..orchestrator import Harness, HarnessConfig
from ..spec import StepSpec, TaskSpec
from .gate_audit import audit


def judge_audit(
    harness: Harness,
    spec: TaskSpec,
    step_number: int,
    mutants_dir: str,
    reference_dir: str | None,
    model: str | None = None,
) -> dict[str, Any]:
    run_id = harness.submit(spec, budget_usd=5.0)
    pins = harness.journal.get_run(run_id).pins
    if model:
        pins["models"]["judge"] = model
    epoch = harness.journal.acquire_lease(run_id, "judge-audit", 3600)
    assert epoch is not None
    counter = {"n": 0}
    assert spec.steps is not None
    requirements = [f"Goal: {spec.goal}", *(f"Constraint: {c}" for c in spec.constraints)] + [
        f"Step {k + 1} ({s.title}): {s.instructions}" for k, s in enumerate(spec.steps[: step_number - 1])
    ]

    def evaluate(ckpt: GitCheckpoint, parent: str, candidate: str, step: StepSpec) -> str:
        counter["n"] += 1
        v = harness.judge.evaluate(
            run_id=run_id,
            epoch=epoch,
            step_index=step_number - 1,
            attempt=counter["n"],
            pins=pins,
            ckpt=ckpt,
            parent=parent,
            candidate=candidate,
            step=step,
            requirements=requirements,
        )
        return v.status

    report = audit(spec, step_number, mutants_dir, reference_dir, evaluate=evaluate)
    report["judge_model"] = pins["models"]["judge"]
    report["spent_usd"] = round(harness.journal.get_run(run_id).spent_usd, 4)
    report["unsure"] = sorted(k for k, v in report["verdicts"].items() if v == "unsure")
    return report


def _provider(name: str):
    if name == "claude-cli":
        from ..providers.claude_cli import ClaudeCliProvider  # type: ignore[import-not-found]

        return ClaudeCliProvider()
    from ..cli import _provider as cli_provider

    return cli_provider(name)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m urh.bench.judge_audit")
    p.add_argument("spec")
    p.add_argument("--step", type=int, required=True)
    p.add_argument("--mutants", required=True)
    p.add_argument("--reference")
    p.add_argument("--provider", default="anthropic")
    p.add_argument("--model", help="judge model id (default: the gateway's judge default)")
    p.add_argument("--out")
    args = p.parse_args(argv)
    spec = TaskSpec.load(args.spec)
    with tempfile.TemporaryDirectory(prefix="urh-judge-audit-") as home:
        h = Harness(os.path.join(home, "h"), _provider(args.provider), config=HarnessConfig())
        report = judge_audit(h, spec, args.step, args.mutants, args.reference, args.model)
        h.journal.close()
    text = json.dumps(report, indent=2)
    if args.out:
        with open(args.out, "w") as f:
            f.write(text)
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
