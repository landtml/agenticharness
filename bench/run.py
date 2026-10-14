"""Planner bench: run each task's goal through the harness and score it against the artifact's metrics.

Every task gives only a goal; the planner writes the steps. The hidden tests are the gate's spec
check, so "done" means they passed in the gate's own checkout. The report counts what the artifact
cares about for a headless run: verified rate, park rate (a park is a failure to minimize), replans,
cost per verified run, and the planner's share of spend.

    python bench/run.py --provider claude-cli --out bench/results/round1.json [task ...]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time

from urh.cli import _provider
from urh.orchestrator import Harness, HarnessConfig
from urh.spec import Check, GateSpec, TaskSpec

HERE = os.path.dirname(os.path.abspath(__file__))


def task_spec(name: str, budget: float) -> TaskSpec:
    d = json.load(open(os.path.join(HERE, "tasks", name, "task.json")))
    gate = GateSpec(
        checks=[Check("hidden", [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "_hidden"])],
        hidden_dir=os.path.join(HERE, "tasks", name, "hidden"),
        protected=["_hidden/"],
    )
    return TaskSpec(goal=d["goal"], constraints=d.get("constraints", []), gate=gate, budget_usd=budget)


def run_task(name: str, provider: str, home: str, budget: float, planner_effort: str) -> dict:
    h = Harness(home, _provider(provider), config=HarnessConfig(planner_effort=planner_effort))
    t0 = time.time()
    rid = h.submit(task_spec(name, budget))
    status = h.run(rid)
    calls = h.journal.model_calls(rid)
    events = h.journal.events(rid)
    by_role: dict[str, float] = {}
    for c in calls:
        by_role[c["role"]] = by_role.get(c["role"], 0.0) + float(c["cost_usd"] or 0.0)
    total = sum(by_role.values())
    return {
        "task": name,
        "status": status,
        "seconds": round(time.time() - t0, 1),
        "steps": h.journal.get_run(rid).step_index,
        "cost_usd": round(total, 4),
        "cost_by_role": {k: round(v, 4) for k, v in by_role.items()},
        "planner_share": round(by_role.get("manager", 0.0) / total, 3) if total else 0.0,
        "plan_calls": [e["why"] for e in events if e["kind"] == "plan"],
        "replans": sum(1 for e in events if e["kind"] == "step_replanned"),
        "replan_failed": sum(1 for e in events if e["kind"] == "replan_failed"),
        "parks": [p["reason"] for p in h.journal.parks(rid)],
        "attempts": len([c for c in calls if c["role"] == "worker"]),
    }


def summarize(rows: list[dict]) -> dict:
    n = len(rows)
    done = [r for r in rows if r["status"] == "done"]
    cost = sum(r["cost_usd"] for r in rows)
    return {
        "tasks": n,
        "verified_rate": round(len(done) / n, 3) if n else 0.0,
        "park_rate": round(sum(1 for r in rows if r["parks"]) / n, 3) if n else 0.0,
        "replans": sum(r["replans"] for r in rows),
        "cost_usd": round(cost, 4),
        "cost_per_verified": round(cost / len(done), 4) if done else None,
        "planner_share": round(sum(r["cost_by_role"].get("manager", 0.0) for r in rows) / cost, 3)
        if cost
        else 0.0,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("tasks", nargs="*")
    ap.add_argument("--provider", default=os.environ.get("URH_PROVIDER", "claude-cli"))
    ap.add_argument("--budget", type=float, default=1.0)
    ap.add_argument("--planner-effort", default="high")
    ap.add_argument("--out")
    args = ap.parse_args()
    names = args.tasks or sorted(os.listdir(os.path.join(HERE, "tasks")))
    rows = []
    with tempfile.TemporaryDirectory(prefix="urh-bench-") as tmp:
        for name in names:
            row = run_task(name, args.provider, os.path.join(tmp, name), args.budget, args.planner_effort)
            print(json.dumps(row), flush=True)
            rows.append(row)
    report = {"summary": summarize(rows), "runs": rows}
    print(json.dumps(report["summary"], indent=2))
    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        json.dump(report, open(args.out, "w"), indent=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
