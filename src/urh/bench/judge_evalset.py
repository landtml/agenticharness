"""Judge audit on a labelled multi-task evalset (the gate thread's format, plain files).

Layout: ``tasks/<task>/spec.md`` (what the worker saw), ``corpus/<task>/*.py`` (candidates, each
the task's ``solution.py``), and ``labels.json`` mapping ``"<task>/<file>"`` to ``{"label": ...}``.
The judge sees the spec and the candidate only, never ``hidden/``, ``manifest.json`` or the file's
name: every candidate is copied in as ``solution.py``, and the order is shuffled.

Reports false accepts (a broken candidate judged ``pass``) and false withholds (a correct one not
judged ``pass``), overall and per task.

Usage: ``python -m urh.bench.judge_evalset EVALSET --provider claude-cli --model claude-haiku-5-5 --out r.json``
"""

from __future__ import annotations

import argparse
import json
import os
import random
import shutil
import tempfile
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from ..checkpoint import GitCheckpoint
from ..orchestrator import Harness, HarnessConfig
from ..spec import StepSpec, TaskSpec
from .gate_audit import _candidate, wilson
from .judge_audit import _provider


def _task(h: Harness, root: str, task: str, items: list[tuple[str, str]], seed: int) -> list[dict[str, Any]]:
    spec_md = open(os.path.join(root, "tasks", task, "spec.md")).read()
    step = StepSpec(title=task, instructions=spec_md, files=["solution.py"])
    spec = TaskSpec(goal=f"Implement the '{task}' task in solution.py as specified.", steps=[step])
    run_id = h.submit(spec, budget_usd=5.0)
    pins = h.journal.get_run(run_id).pins
    epoch = h.journal.acquire_lease(run_id, f"judge-evalset-{task}", 86400)
    assert epoch is not None
    rows = []
    order = list(items)
    random.Random(seed).shuffle(order)
    with tempfile.TemporaryDirectory(prefix=f"urh-evalset-{task}-") as tmp:
        ckpt = GitCheckpoint(os.path.join(tmp, "repo"))
        base = ckpt.init(None)
        for n, (fname, label) in enumerate(order, start=1):
            overlay = os.path.join(tmp, f"c{n}")
            os.makedirs(overlay)
            shutil.copy(os.path.join(root, "corpus", task, fname), os.path.join(overlay, "solution.py"))
            commit = _candidate(ckpt, n, base, overlay)
            try:
                v = h.judge.evaluate(
                    run_id=run_id,
                    epoch=epoch,
                    step_index=0,
                    attempt=n,
                    pins=pins,
                    ckpt=ckpt,
                    parent=base,
                    candidate=commit,
                    step=step,
                    requirements=[f"Goal: {spec.goal}"],
                )
                verdict, reasons = v.status, v.failures[:2]
            except Exception as e:  # one bad call should not sink the audit
                verdict, reasons = "error", [repr(e)[:200]]
            rows.append({"task": task, "file": fname, "label": label, "verdict": verdict, "reasons": reasons})
    return rows


def run(root: str, h: Harness, tasks: list[str] | None, seed: int, workers: int) -> dict[str, Any]:
    labels = json.load(open(os.path.join(root, "labels.json")))
    by_task: dict[str, list[tuple[str, str]]] = {}
    for key, meta in labels.items():
        task, fname = key.split("/", 1)
        if meta["label"] not in ("broken", "correct") or (tasks and task not in tasks):
            continue  # ambiguous rulings are excluded
        by_task.setdefault(task, []).append((fname, meta["label"]))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = [pool.submit(_task, h, root, t, items, seed) for t, items in sorted(by_task.items())]
        rows = [r for f in futs for r in f.result()]

    def score(rs: list[dict[str, Any]]) -> dict[str, Any]:
        broken = [r for r in rs if r["label"] == "broken"]
        correct = [r for r in rs if r["label"] == "correct"]
        fa = sum(r["verdict"] == "pass" for r in broken)
        fw = sum(r["verdict"] != "pass" for r in correct)
        return {
            "broken": len(broken),
            "false_accepts": fa,
            "false_accept_interval95": [round(x, 4) for x in wilson(fa, len(broken))],
            "correct": len(correct),
            "false_withholds": fw,
            "unsure": sum(r["verdict"] == "unsure" for r in rs),
            "errors": sum(r["verdict"] == "error" for r in rs),
        }

    return {
        "overall": score(rows),
        "per_task": {t: score([r for r in rows if r["task"] == t]) for t in sorted(by_task)},
        "rows": rows,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m urh.bench.judge_evalset")
    p.add_argument("evalset")
    p.add_argument("--provider", default="anthropic")
    p.add_argument("--model")
    p.add_argument("--tasks", nargs="*")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--workers", type=int, default=8)
    p.add_argument("--out")
    args = p.parse_args(argv)
    with tempfile.TemporaryDirectory(prefix="urh-judge-evalset-") as home:
        models = {"judge": args.model} if args.model else None
        cfg = HarnessConfig(**({"models": {**HarnessConfig().models, **models}} if models else {}))
        h = Harness(os.path.join(home, "h"), _provider(args.provider), config=cfg)
        report = run(args.evalset, h, args.tasks, args.seed, args.workers)
        report["judge_model"] = h.gateway.pins_for(cfg.models)["models"]["judge"]
        report["spent_usd"] = round(sum(r.spent_usd for r in h.journal.list_runs()), 4)
        h.journal.close()
    if args.out:
        with open(args.out, "w") as f:
            json.dump(report, f, indent=2)
    print(json.dumps({k: report[k] for k in ("overall", "per_task", "judge_model", "spent_usd")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
