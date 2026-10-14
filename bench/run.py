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
import shutil
import subprocess
import sys
import tempfile
import time

from urh.cli import _provider
from urh.orchestrator import Harness, HarnessConfig
from urh.spec import Check, GateSpec, StepSpec, TaskSpec
from urh.stats import compute as journal_stats

OUTAGE_WAKE_S = 120.0
MAX_AUTO_WAKES = 6
HERE = os.path.dirname(os.path.abspath(__file__))


def task_spec(name: str, budget: float) -> TaskSpec:
    d = json.load(open(os.path.join(HERE, "tasks", name, "task.json")))
    gate = GateSpec(
        checks=[Check("hidden", [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "_hidden"])],
        hidden_dir=os.path.join(HERE, "tasks", name, "hidden"),
        protected=["_hidden/"],
    )
    return TaskSpec(goal=d["goal"], constraints=d.get("constraints", []), gate=gate, budget_usd=budget)


def baseline_spec(name: str, budget: float) -> TaskSpec:
    """The plain loop: one worker gets the whole goal and its word is final. No planner, no real gate."""
    d = json.load(open(os.path.join(HERE, "tasks", name, "task.json")))
    gate = GateSpec(checks=[Check("none", ["true"])])
    step = StepSpec(title="goal", instructions=d["goal"], checks=["none"])
    return TaskSpec(
        goal=d["goal"],
        constraints=d.get("constraints", []),
        gate=gate,
        steps=[step],
        budget_usd=budget,
        max_repairs=0,
        max_worker_turns=60,
    )


def hidden_pass(home: str, rid: str, name: str) -> bool:
    """Score the final verified tree against the hidden tests, outside the harness."""
    with tempfile.TemporaryDirectory() as tree:
        repo = os.path.join(home, "runs", rid, "repo.git")
        subprocess.run(["git", "clone", "-q", "-b", "verified", repo, tree], check=True, capture_output=True)
        shutil.copytree(os.path.join(HERE, "tasks", name, "hidden"), os.path.join(tree, "_hidden"))
        cmd = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "_hidden"]
        return subprocess.run(cmd, cwd=tree, capture_output=True, timeout=300).returncode == 0


def run_task(name: str, provider: str, home: str, budget: float, planner_effort: str, mode: str) -> dict:
    cfg = HarnessConfig(planner_effort=planner_effort, outage_wake_s=OUTAGE_WAKE_S)
    h = Harness(home, _provider(provider), config=cfg)
    t0 = time.time()
    spec = baseline_spec(name, budget) if mode == "plain" else task_spec(name, budget)
    rid = h.submit(spec)
    status = h.run(rid)
    wakes = 0
    # Behave like the daemon: a park that wakes itself (an outage) is retried after its cooldown.
    while status == "parked" and wakes < MAX_AUTO_WAKES:
        due = [p["preconditions"].get("wake_at") for p in h.journal.parks(rid, status="open")]
        if not due or None in due:
            break
        time.sleep(max(0.0, max(due) - time.time()) + 1)
        if rid not in h.wake_due():
            break
        wakes += 1
        status = h.run(rid)
    passed = hidden_pass(home, rid, name)
    calls = h.journal.model_calls(rid)
    events = h.journal.events(rid)
    by_role: dict[str, float] = {}
    for c in calls:
        by_role[c["role"]] = by_role.get(c["role"], 0.0) + float(c["cost_usd"] or 0.0)
    total = sum(by_role.values())
    return {
        "task": name,
        "mode": mode,
        "status": status,
        "hidden_pass": passed,
        "false_done": status == "done" and not passed,
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
        "auto_wakes": wakes,
        "escalations": sum(1 for e in events if e["kind"] == "escalated"),
        "escalations_skipped": sum(1 for e in events if e["kind"] == "escalation_skipped"),
        "stats": journal_stats(h.journal),
    }


def summarize(rows: list[dict]) -> dict:
    n = len(rows)
    done = [r for r in rows if r["status"] == "done" and r["hidden_pass"]]
    cost = sum(r["cost_usd"] for r in rows)
    return {
        "tasks": n,
        "verified_rate": round(len(done) / n, 3) if n else 0.0,
        "park_rate": round(sum(1 for r in rows if r["parks"]) / n, 3) if n else 0.0,
        "false_done": sum(1 for r in rows if r["false_done"]),
        "crashes": sum(1 for r in rows if r["status"] == "crash"),
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
    ap.add_argument("--planner-effort", default="medium")
    ap.add_argument("--mode", choices=["harness", "plain"], default="harness")
    ap.add_argument("--repeat", type=int, default=1)
    ap.add_argument("--out")
    ap.add_argument("--keep", help="keep each run's harness home (journal, blobs, repo) under this directory")
    args = ap.parse_args()
    names = args.tasks or sorted(os.listdir(os.path.join(HERE, "tasks")))
    rows = []
    with tempfile.TemporaryDirectory(prefix="urh-bench-") as scratch:
        tmp = args.keep or scratch
        for k, name in enumerate(n for n in names for _ in range(args.repeat)):
            home = os.path.join(tmp, f"{name}-{k}")
            try:
                row = run_task(name, args.provider, home, args.budget, args.planner_effort, args.mode)
            except Exception as e:  # a harness crash is a result, and the worst one
                row = {
                    "task": name,
                    "mode": args.mode,
                    "status": "crash",
                    "error": repr(e)[:500],
                    "hidden_pass": False,
                    "false_done": False,
                    "cost_usd": 0.0,
                    "cost_by_role": {},
                    "replans": 0,
                    "parks": [],
                }
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
