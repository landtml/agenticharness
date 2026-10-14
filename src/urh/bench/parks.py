"""Parks bench: how often a run needs a person, under round-1 vs current self-resolving policies.

Each scenario injects one kind of trouble into a two-step task driven by the
scripted provider (no model spend). Under the ``strict`` policy every trouble
parks for a person, as in round 1. Under ``headless`` the harness is expected
to resolve it itself: budget top-up within an allowance, outage wake after the
breaker closes, a blind judge for checks no script covers, and one escalation
attempt before giving up. A scenario that still needs a person under
``headless`` is a real park and the number to drive down.

Usage: ``python -m urh.bench.parks --out report.json``
"""

from __future__ import annotations

import argparse
import copy
import json
import random
import tempfile
from collections.abc import Callable
from typing import Any

from .. import stats
from ..orchestrator import Harness, HarnessConfig
from ..spec import TaskSpec
from ..testing import ScriptedProvider
from .chaos import build_task

POLICIES: dict[str, dict[str, Any]] = {
    "strict": {"escalate": False, "use_judge": False, "auto_topup_usd": 0.0, "outage_wake_s": 1e9},
    "headless": {
        "escalate": True,
        "use_judge": True,
        "auto_topup_usd": 0.5,
        "max_auto_topups": 2,
        "outage_wake_s": 0.0,
    },
}

Mutator = Callable[[dict[str, Any], dict[str, Any]], None]


def _wrong(spec: dict[str, Any], script: dict[str, Any], attempts: list[int]) -> None:
    """Step 2 writes a wrong value on the given attempts; any later attempt writes the right one."""
    for a in attempts:
        script["steps"][f"2@{a}" if a > 1 else "2"] = [
            [{"write": "f1.py", "content": "def value():\n    return -1\n"}],
            [{"finish": "f1 done"}],
        ]
    fix = max(attempts) + 1
    script["steps"][f"2@{fix}"] = [
        [{"write": "f1.py", "content": "def value():\n    return 7\n"}],
        [{"finish": "f1 fixed"}],
    ]


def _budget(spec: dict[str, Any], script: dict[str, Any]) -> None:
    spec["budget_usd"] = 0.0001


def _outage(spec: dict[str, Any], script: dict[str, Any]) -> None:
    script["fail_calls"] = 3


def _unscripted(spec: dict[str, Any], script: dict[str, Any]) -> None:
    spec["steps"][1]["checks"] = []


def _hard(spec: dict[str, Any], script: dict[str, Any]) -> None:
    _wrong(spec, script, [1, 2])  # max_repairs=1: two failures exhaust repairs


def _stuck(spec: dict[str, Any], script: dict[str, Any]) -> None:
    _wrong(spec, script, [1, 2])  # attempt 2 repeats attempt 1 byte for byte


def _hopeless(spec: dict[str, Any], script: dict[str, Any]) -> None:
    _wrong(spec, script, [1, 2, 3, 4, 5])  # even the escalation attempt fails


def _runaway(spec: dict[str, Any], script: dict[str, Any]) -> None:
    spec["budget_usd"] = 0.0001
    script["huge_usage"] = True  # each call costs more than every allowed top-up together


# scenario -> (mutator, what a correct harness does under the headless policy)
SCENARIOS: dict[str, tuple[Mutator, str]] = {
    "clean": (lambda spec, script: None, "done"),
    "budget_shortfall": (_budget, "done"),
    "provider_outage": (_outage, "done"),
    "no_script_check": (_unscripted, "done"),
    "hard_step": (_hard, "done"),
    "no_progress_repair": (_stuck, "done"),
    # a person really is needed: parking is the right answer, finishing would be a lie
    "hopeless_step": (_hopeless, "parked"),
    "runaway_cost": (_runaway, "parked"),
}


def run_scenario(name: str, policy: str, seed: int = 0) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="urh-parks-") as work:
        spec_d, script = build_task(work, 2, random.Random(seed))
        for turn in script["steps"].values():  # no sleeps: this bench is about decisions, not timing
            for t in turn:
                t[:] = [a for a in t if "sleep" not in a and "effect" not in a]
        SCENARIOS[name][0](spec_d, script)
        h = Harness(
            f"{work}/home", ScriptedProvider(copy.deepcopy(script)), config=HarnessConfig(**POLICIES[policy])
        )
        if policy == "headless":
            h.gateway.breaker.cooldown_s = 0.0  # stands in for the cooldown having elapsed
        rid = h.submit(TaskSpec.from_dict(spec_d), budget_usd=spec_d["budget_usd"])
        status = h.run(rid)
        for _ in range(3):  # the daemon's next ticks: only self-waking parks move
            status = h.run_pending().get(rid, status)
        s = stats.compute(h.journal)
        return {
            "scenario": name,
            "policy": policy,
            "status": status,
            "expected": SCENARIOS[name][1] if policy == "headless" else None,
            "human_touches": s["human_touches"],
            "parks": [p["reason"] for p in h.journal.parks(rid)],
            "calls_by_role": s["calls_by_role"],
            "spent_usd": round(h.journal.get_run(rid).spent_usd, 6),
        }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m urh.bench.parks")
    p.add_argument("--out")
    args = p.parse_args(argv)
    rows = [run_scenario(n, pol) for pol in POLICIES for n in SCENARIOS]
    summary = {
        pol: {
            "scenarios": len(SCENARIOS),
            "needed_a_person": sum(1 for r in rows if r["policy"] == pol and r["human_touches"]),
            "done": sum(1 for r in rows if r["policy"] == pol and r["status"] == "done"),
            # avoidable: parked where the harness could have finished; wrong_finish: done where it had to stop
            "avoidable_parks": sum(
                1
                for r in rows
                if r["policy"] == pol and r["status"] == "parked" and SCENARIOS[r["scenario"]][1] == "done"
            ),
            "wrong_finishes": sum(
                1
                for r in rows
                if r["policy"] == pol and r["status"] == "done" and SCENARIOS[r["scenario"]][1] != "done"
            ),
        }
        for pol in POLICIES
    }
    report = {"summary": summary, "scenarios": rows}
    if args.out:
        with open(args.out, "w") as f:
            json.dump(report, f, indent=2)
    for r in rows:
        print(
            f"{r['policy']:9} {r['scenario']:20} {r['status']:7} touches={r['human_touches']} parks={r['parks']}"
        )
    print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
