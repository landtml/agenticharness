"""Chaos bench: kill -9 the harness at random moments and measure what the recipe says matters.

For each trial a fresh run of an N-step task (one outward effect per step) is
driven by a child process that is SIGKILLed after a random delay, restarted
after its lease expires, and killed again, until the run finishes. Metrics:

- ``duplicate_effects``: deliveries beyond one per effect key (target: 0)
- ``redone_verified_steps``: attempts started on a step after it had passed (target: 0)
- ``redone_call_fraction``: worker calls in aborted attempts / all worker calls (the D1 price of crashes)
- ``completed``: runs that reached ``done`` with every expected file in the verified tree

Usage: ``python -m urh.bench.chaos --trials 20 --steps 3 --out report.json``
"""

from __future__ import annotations

import argparse
import json
import os
import random
import signal
import subprocess
import sys
import tempfile
import time
from typing import Any

from ..checkpoint import GitCheckpoint
from ..journal import Journal
from ..orchestrator import Harness, HarnessConfig
from ..spec import TaskSpec
from ..testing import ScriptedProvider


def build_task(workdir: str, steps: int, rng: random.Random) -> tuple[dict[str, Any], dict[str, Any]]:
    hidden = os.path.join(workdir, "hidden")
    os.makedirs(hidden, exist_ok=True)
    spec_steps, script_steps, checks = [], {}, []
    for i in range(steps):
        name = f"f{i}"
        with open(os.path.join(hidden, f"test_{name}.py"), "w") as f:
            f.write(f"from {name} import value\n\ndef test_{name}():\n    assert value() == {i * 7}\n")
        checks.append(
            {
                "name": name,
                "cmd": [
                    sys.executable,
                    "-m",
                    "pytest",
                    "-q",
                    "-p",
                    "no:cacheprovider",
                    f"_hidden/test_{name}.py",
                ],
            }
        )
        spec_steps.append(
            {
                "title": name,
                "instructions": f"Write {name}.py with value() returning {i * 7}.",
                "files": [f"{name}.py"],
                "checks": [name],
            }
        )
        jitter = [{"sleep": round(rng.uniform(0.0, 0.15), 3)}]
        script_steps[str(i + 1)] = [
            jitter
            + [
                {"write": f"{name}.py", "content": f"def value():\n    return {i * 7}\n"},
                {"effect": "outbox_file", "payload": {"step": i}},
            ],
            jitter + [{"finish": f"{name} done"}],
        ]
    spec = {
        "goal": "chaos task",
        "gate": {"hidden_dir": hidden, "checks": checks, "protected": ["_hidden/"]},
        "steps": spec_steps,
        "budget_usd": 1.0,
        "max_repairs": 1,
    }
    return spec, {"steps": script_steps}


FAULT_POINTS = (
    "effect_delivered",
    "before_promote",
    "before_complete_step",
    "after_complete_step",
    "after_gate",
    "after_verdict",
)


def run_trial(
    seed: int,
    steps: int,
    lease_ttl: float,
    effect_delay: float,
    max_kills: int,
    kill_window: tuple[float, float],
    fault: str | None = None,
) -> dict[str, Any]:
    rng = random.Random(seed)
    with tempfile.TemporaryDirectory(prefix="urh-chaos-") as work:
        spec_d, script = build_task(work, steps, rng)
        script_path = os.path.join(work, "script.json")
        with open(script_path, "w") as f:
            json.dump(script, f)
        home = os.path.join(work, "home")
        h = Harness(home, ScriptedProvider(script), config=HarnessConfig(lease_ttl=lease_ttl))
        run_id = h.submit(TaskSpec.from_dict(spec_d))
        h.journal.close()

        kills, status, t0 = 0, "", time.time()
        env = dict(os.environ)
        if fault:
            env.update({"URH_FAULT": fault, "URH_FAULT_MARKER": os.path.join(work, "fault.marker")})
        while True:
            proc = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "urh.bench.chaos_child",
                    home,
                    script_path,
                    run_id,
                    str(lease_ttl),
                    str(effect_delay),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
            )
            if kills < max_kills:
                try:
                    out, _ = proc.communicate(timeout=rng.uniform(*kill_window))
                    status = out.strip()
                except subprocess.TimeoutExpired:
                    os.kill(proc.pid, signal.SIGKILL)
                    proc.wait()
                    kills += 1
                    time.sleep(lease_ttl + 0.2)
                    continue
            else:
                out, err = proc.communicate(timeout=300)
                status = out.strip()
            if proc.returncode == -signal.SIGKILL and not status:
                kills += 1  # a fault point killed the process
                time.sleep(lease_ttl + 0.2)
                continue
            if not status:
                status = f"error: exit {proc.returncode}"
            if status in ("done", "failed", "parked") or status.startswith("error"):
                break

        j = Journal(os.path.join(home, "journal.sqlite"))
        run = j.get_run(run_id)
        attempts = j.attempts(run_id)
        calls = [c for c in j.model_calls(run_id) if c["role"] == "worker"]
        aborted = {(a["step_index"], a["attempt"]) for a in attempts if a["status"] == "aborted"}
        redone_calls = sum(1 for c in calls if (c["step_index"], c["attempt"]) in aborted)
        redone_steps = 0
        for idx in range(steps):
            step_attempts = sorted(
                (a for a in attempts if a["step_index"] == idx), key=lambda a: a["attempt"]
            )
            passed = [a for a in step_attempts if a["status"] == "pass"]
            if passed:
                redone_steps += sum(1 for a in step_attempts if a["attempt"] > passed[0]["attempt"])
        dispatch_epoch: dict[str, int] = {}
        recoveries = 0
        for e in j.events(run_id):
            if e["kind"] == "effect_dispatching":
                dispatch_epoch.setdefault(e["key"], e["epoch"])
            elif (
                e["kind"] == "effect_done"
                and e["key"] in dispatch_epoch
                and e["epoch"] != dispatch_epoch[e["key"]]
            ):
                recoveries += 1
        log_path = os.path.join(home, "outbox", "deliveries.log")
        deliveries = open(log_path).read().split() if os.path.exists(log_path) else []
        files_ok = False
        if run.verified_commit:
            tree = (
                GitCheckpoint(os.path.join(home, "runs", run_id))
                ._git("ls-tree", "-r", "--name-only", run.verified_commit)
                .decode()
                .split()
            )
            files_ok = all(f"f{i}.py" in tree for i in range(steps))
        return {
            "seed": seed,
            "fault": fault,
            "status": run.status,
            "kills": kills,
            "seconds": round(time.time() - t0, 2),
            "completed": run.status == "done" and files_ok,
            "effects": len(set(deliveries)),
            "duplicate_effects": len(deliveries) - len(set(deliveries)),
            "redone_verified_steps": redone_steps,
            # effects whose dispatch was interrupted by a kill and settled later by read-back or keyed resend
            "effect_crash_recoveries": recoveries,
            "worker_calls": len(calls),
            "redone_calls": redone_calls,
            "lost_calls": sum(1 for c in j.model_calls(run_id) if c["status"] == "lost"),
            "spent_usd": run.spent_usd,
        }


def summarize(trials: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(trials)
    calls = sum(t["worker_calls"] for t in trials) or 1
    return {
        "trials": n,
        "kills": sum(t["kills"] for t in trials),
        "completed": sum(t["completed"] for t in trials),
        "duplicate_effects": sum(t["duplicate_effects"] for t in trials),
        "redone_verified_steps": sum(t["redone_verified_steps"] for t in trials),
        "effect_crash_recoveries": sum(t["effect_crash_recoveries"] for t in trials),
        "redone_call_fraction": round(sum(t["redone_calls"] for t in trials) / calls, 4),
        "lost_calls": sum(t["lost_calls"] for t in trials),
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m urh.bench.chaos")
    p.add_argument("--trials", type=int, default=10)
    p.add_argument("--steps", type=int, default=3)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--lease-ttl", type=float, default=1.0)
    p.add_argument("--effect-delay", type=float, default=0.2)
    p.add_argument("--max-kills", type=int, default=3)
    p.add_argument("--faults", action="store_true", help="also run one trial per deterministic fault point")
    p.add_argument("--out")
    args = p.parse_args(argv)
    trials = [
        run_trial(args.seed + i, args.steps, args.lease_ttl, args.effect_delay, args.max_kills, (0.3, 2.5))
        for i in range(args.trials)
    ]
    if args.faults:
        trials += [
            run_trial(args.seed + 1000 + k, args.steps, args.lease_ttl, args.effect_delay, 0, (0, 0), fault=f)
            for k, f in enumerate(FAULT_POINTS)
        ]
    report = {"summary": summarize(trials), "trials": trials}
    text = json.dumps(report, indent=2)
    if args.out:
        with open(args.out, "w") as f:
            f.write(text)
    print(json.dumps(report["summary"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
