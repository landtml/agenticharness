"""The example's gate must accept the reference and refuse every mutant in the hand-written corpus."""

import os
import sys

from urh.bench.gate_audit import audit, wilson
from urh.spec import TaskSpec

EX = os.path.join(os.path.dirname(__file__), "..", "examples", "slug")


def test_wilson_interval_brackets_rate():
    lo, hi = wilson(4, 15)
    assert lo < 4 / 15 < hi


def test_slug_gate_refuses_hand_written_mutants():
    spec = TaskSpec.load(os.path.join(EX, "spec.json"))
    for check in spec.gate.checks:
        if check.cmd[0] == "python":
            check.cmd[0] = sys.executable
    report = audit(spec, 2, os.path.join(EX, "mutants"), os.path.join(EX, "reference"))
    assert report["reference_accepted"] is True
    assert report["accepted"] == []


def test_judge_audit_counts_unsure_as_not_accepted(tmp_path):
    from urh.bench.judge_audit import judge_audit
    from urh.orchestrator import Harness, HarnessConfig
    from urh.testing import ScriptedProvider

    spec = TaskSpec.load(os.path.join(EX, "spec.json"))
    script = {
        "steps": {},
        "judge": [{"verdict": "pass", "reasons": []}] + [{"verdict": "unsure", "reasons": []}] * 40,
    }
    h = Harness(str(tmp_path / "h"), ScriptedProvider(script), config=HarnessConfig())
    r = judge_audit(h, spec, 2, os.path.join(EX, "mutants"), os.path.join(EX, "reference"))
    assert r["reference_accepted"] is True
    assert r["false_accept_rate"] == 0.0 and len(r["unsure"]) == r["mutants"]
