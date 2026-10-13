"""Command line: submit runs, drive them headless, answer parked questions."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

from .gateway import AnthropicProvider, Provider
from .orchestrator import Harness, HarnessConfig
from .spec import TaskSpec


def _provider(name: str) -> Provider:
    if name.startswith("scripted:"):
        from .testing import ScriptedProvider

        return ScriptedProvider.from_file(name.split(":", 1)[1])
    if name == "anthropic":
        return AnthropicProvider()
    raise SystemExit(f"unknown provider {name!r} (use 'anthropic' or 'scripted:PATH')")


def _harness(args: argparse.Namespace) -> Harness:
    cfg = HarnessConfig(lease_ttl=args.lease_ttl, heartbeat_s=args.heartbeat,
                        provider_backoff_s=float(os.environ.get("URH_BACKOFF_S", "2.0")))
    return Harness(args.home, _provider(args.provider), config=cfg)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="urh", description="Upper-Right Harness")
    p.add_argument("--home", default=os.environ.get("URH_HOME", ".urh"))
    p.add_argument("--provider", default=os.environ.get("URH_PROVIDER", "anthropic"))
    p.add_argument("--lease-ttl", type=float, default=float(os.environ.get("URH_LEASE_TTL", "30")))
    p.add_argument("--heartbeat", type=float, default=float(os.environ.get("URH_HEARTBEAT", "10")))
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("submit", help="create a run from a spec file")
    s.add_argument("spec")
    s.add_argument("--dedupe")
    s.add_argument("--budget", type=float)

    r = sub.add_parser("run", help="drive one run, or every runnable run")
    r.add_argument("run_id", nargs="?")

    d = sub.add_parser("daemon", help="keep driving runnable runs")
    d.add_argument("--interval", type=float, default=5.0)

    st = sub.add_parser("status", help="show runs")
    st.add_argument("run_id", nargs="?")

    sub.add_parser("parks", help="list open parked questions")
    a = sub.add_parser("answer", help="answer a parked question (requeues the run)")
    a.add_argument("park_id")
    a.add_argument("text")
    b = sub.add_parser("add-budget", help="raise a run's budget")
    b.add_argument("run_id")
    b.add_argument("amount", type=float)
    c = sub.add_parser("calls", help="show a run's model-call log")
    c.add_argument("run_id")

    args = p.parse_args(argv)
    h = _harness(args)
    j = h.journal

    if args.cmd == "submit":
        print(h.submit(TaskSpec.load(args.spec), dedupe_key=args.dedupe, budget_usd=args.budget))
    elif args.cmd == "run":
        if args.run_id:
            print(h.run(args.run_id))
        else:
            for rid, status in h.run_pending().items():
                print(rid, status)
    elif args.cmd == "daemon":
        while True:
            h.run_pending()
            time.sleep(args.interval)
    elif args.cmd == "status":
        runs = [j.get_run(args.run_id)] if args.run_id else j.list_runs()
        for run in runs:
            print(json.dumps({
                "id": run.id, "status": run.status, "reason": run.status_reason, "step": run.step_index,
                "spent_usd": round(run.spent_usd, 6), "budget_usd": run.budget_usd,
                "verified_commit": run.verified_commit,
            }))
    elif args.cmd == "parks":
        for pk in j.parks(status="open"):
            print(json.dumps({"id": pk["id"], "run_id": pk["run_id"], "reason": pk["reason"],
                              "question": pk["question"]}))
    elif args.cmd == "answer":
        print(j.answer_park(args.park_id, args.text))
    elif args.cmd == "add-budget":
        j.add_budget(args.run_id, args.amount)
    elif args.cmd == "calls":
        for call in j.model_calls(args.run_id):
            print(json.dumps({k: call[k] for k in ("step_index", "attempt", "call_index", "role", "model", "status",
                                                   "cost_usd", "input_tokens", "output_tokens", "cache_read")}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
