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
