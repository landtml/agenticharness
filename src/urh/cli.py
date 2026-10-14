"""Command line: submit runs, drive them headless, answer parked questions."""

from __future__ import annotations

import argparse
import json
import os
import sys

from . import notify, server, stats
from .gateway import AnthropicProvider, Provider
from .orchestrator import Harness, HarnessConfig
from .runtime import Runtime
from .sessions import Sessions
from .spec import TaskSpec


def _provider(name: str) -> Provider:
    if name.startswith("scripted:"):
        from .testing import ScriptedProvider

        return ScriptedProvider.from_file(name.split(":", 1)[1])
    if name == "anthropic":
        return AnthropicProvider()
    if name == "claude-cli":
        # A signed-in Claude Code CLI as transport; no API key needed.
        from .providers.claude_cli import ClaudeCliProvider

        return ClaudeCliProvider()
    if name.startswith("openai-compatible:"):
        # e.g. openai-compatible:https://openrouter.ai/api/v1 with OPENAI_API_KEY set
        from .providers.openai_compat import OpenAICompatibleProvider

        return OpenAICompatibleProvider(
            name.split(":", 1)[1], api_key_env=os.environ.get("URH_API_KEY_ENV", "OPENAI_API_KEY")
        )
    raise SystemExit(
        f"unknown provider {name!r} (use 'anthropic', 'claude-cli', 'openai-compatible:URL' or 'scripted:PATH')"
    )


def _harness(args: argparse.Namespace) -> Harness:
    cfg = HarnessConfig(
        lease_ttl=args.lease_ttl,
        heartbeat_s=args.heartbeat,
        provider_backoff_s=float(os.environ.get("URH_BACKOFF_S", "2.0")),
    )
    return Harness(args.home, _provider(args.provider), config=cfg)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="urh", description="Upper-Right Harness")
    p.add_argument("--home", default=os.environ.get("URH_HOME", ".urh"))
    p.add_argument("--provider", default=os.environ.get("URH_PROVIDER", "anthropic"))
    p.add_argument("--lease-ttl", type=float, default=float(os.environ.get("URH_LEASE_TTL", "30")))
    p.add_argument("--heartbeat", type=float, default=float(os.environ.get("URH_HEARTBEAT", "10")))
    p.add_argument(
        "--models",
        default=os.environ.get("URH_MODELS"),
        help='role-to-model JSON, e.g. \'{"manager": "...", "worker": "..."}\'',
    )
    p.add_argument(
        "--prices",
        default=os.environ.get("URH_PRICES"),
        help="JSON file of per-model prices (USD per MTok) for models the built-in book lacks",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("submit", help="create a run from a spec file")
    s.add_argument("spec")
    s.add_argument("--dedupe")
    s.add_argument("--budget", type=float)

    r = sub.add_parser("run", help="drive one run, or every runnable run")
    r.add_argument("run_id", nargs="?")

    d = sub.add_parser("daemon", help="fire triggers, wake parks and drive runnable runs, without an API")
    d.add_argument("--interval", type=float, default=5.0)
    d.add_argument("--workers", type=int, help="runs driven at once (default: config max_active_runs)")

    sv = sub.add_parser("serve", help="the daemon plus the HTTP API (token from URH_API_TOKEN)")
    sv.add_argument("--host", default=os.environ.get("URH_HOST", "127.0.0.1"))
    sv.add_argument("--port", type=int, default=int(os.environ.get("URH_PORT", "8787")))
    sv.add_argument("--interval", type=float, default=1.0)
    sv.add_argument("--workers", type=int)

    se = sub.add_parser("session", help="headless sessions: follow-up tasks over one evolving codebase")
    ses = se.add_subparsers(dest="session_cmd", required=True)
    sn = ses.add_parser("new", help="start a session from a template spec (its goal and steps are ignored)")
    sn.add_argument("template")
    sn.add_argument("--title", default="session")
    sn.add_argument("--budget", type=float, default=1.0, help="budget per message")
    ss = ses.add_parser("send", help="add a message; it runs once the previous one has finished")
    ss.add_argument("session_id")
    ss.add_argument("text")
    ss.add_argument(
        "--check", action="append", dest="checks", help="gate check this message adds (repeatable)"
    )
    ses.add_parser("show").add_argument("session_id")
    ses.add_parser("list")

    tr = sub.add_parser("trigger", help="manage cron and webhook triggers")
    trs = tr.add_subparsers(dest="trigger_cmd", required=True)
    tc = trs.add_parser("add-cron", help="start a run from SPEC on a cron schedule (UTC)")
    tc.add_argument("name")
    tc.add_argument("schedule", help="5-field cron or @hourly/@daily/...")
    tc.add_argument("spec")
    tc.add_argument("--budget", type=float)
    tw = trs.add_parser("add-webhook", help="start a run from SPEC on each signed POST /hooks/NAME")
    tw.add_argument("name")
    tw.add_argument("spec")
    tw.add_argument("--secret-env", default="URH_WEBHOOK_SECRET", help="env var holding the HMAC secret")
    tw.add_argument("--budget", type=float)
    trs.add_parser("list")
    for verb in ("rm", "enable", "disable"):
        trs.add_parser(verb).add_argument("name")

    st = sub.add_parser("status", help="show runs")
    st.add_argument("run_id", nargs="?")

    sub.add_parser("parks", help="list open parked questions")
    a = sub.add_parser("answer", help="answer a parked question (requeues the run)")
    a.add_argument("park_id")
    a.add_argument("text")
    b = sub.add_parser("add-budget", help="raise a run's budget")
    b.add_argument("run_id")
    b.add_argument("amount", type=float)
    sub.add_parser("stats", help="outcome metrics: park rate, cost and calls per verified run")
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
    elif args.cmd in ("daemon", "serve"):
        if args.workers:
            h.config.max_active_runs = args.workers
        rt = Runtime(h, notifiers=notify.from_env())
        if args.cmd == "daemon":
            try:
                rt.serve(args.interval)
            except KeyboardInterrupt:
                rt.stop()
        else:
            token = os.environ.get("URH_API_TOKEN", "")
            if len(token) < 16:
                raise SystemExit("set URH_API_TOKEN (16+ characters) to serve the API")
            server.serve(rt, token, args.host, args.port, args.interval)
    elif args.cmd == "session":
        sessions = Sessions(h)
        sc = args.session_cmd
        if sc == "new":
            with open(args.template) as f:
                raw = json.load(f)
            template = TaskSpec.from_dict(
                {"goal": "-", **raw}, os.path.dirname(os.path.abspath(args.template))
            )
            tpl = {k: v for k, v in template.to_dict().items() if k not in ("goal", "steps")}
            print(sessions.create(args.title, tpl, args.budget))
        elif sc == "send":
            print(sessions.send(args.session_id, args.text, args.checks))
        elif sc == "show":
            print(json.dumps(sessions.view(args.session_id), indent=2))
        else:
            for row in j.list_sessions():
                print(json.dumps(row))
    elif args.cmd == "trigger":
        rt = Runtime(h)
        tc_ = args.trigger_cmd
        if tc_ == "add-cron":
            print(rt.add_cron(args.name, args.schedule, TaskSpec.load(args.spec), args.budget))
        elif tc_ == "add-webhook":
            secret = os.environ.get(args.secret_env, "")
            print(rt.add_webhook(args.name, TaskSpec.load(args.spec), secret, args.budget))
        elif tc_ == "list":
            for t in j.list_triggers():
                print(
                    json.dumps(
                        {k: t[k] for k in ("name", "kind", "schedule", "enabled", "next_fire_at", "fired")}
                    )
                )
        elif tc_ == "rm":
            j.delete_trigger(args.name)
        else:
            j.set_trigger_enabled(args.name, tc_ == "enable")
    elif args.cmd == "status":
        runs = [j.get_run(args.run_id)] if args.run_id else j.list_runs()
        for run in runs:
            print(
                json.dumps(
                    {
                        "id": run.id,
                        "status": run.status,
                        "reason": run.status_reason,
                        "step": run.step_index,
                        "spent_usd": round(run.spent_usd, 6),
                        "budget_usd": run.budget_usd,
                        "verified_commit": run.verified_commit,
                    }
                )
            )
    elif args.cmd == "parks":
        for pk in j.parks(status="open"):
            print(
                json.dumps(
                    {
                        "id": pk["id"],
                        "run_id": pk["run_id"],
                        "reason": pk["reason"],
                        "question": pk["question"],
                    }
                )
            )
    elif args.cmd == "answer":
        print(j.answer_park(args.park_id, args.text))
    elif args.cmd == "stats":
        print(json.dumps(stats.compute(j), indent=2))
    elif args.cmd == "add-budget":
        j.add_budget(args.run_id, args.amount)
    elif args.cmd == "calls":
        for call in j.model_calls(args.run_id):
            print(
                json.dumps(
                    {
                        k: call[k]
                        for k in (
                            "step_index",
                            "attempt",
                            "call_index",
                            "role",
                            "model",
                            "status",
                            "cost_usd",
                            "input_tokens",
                            "output_tokens",
                            "cache_read",
                        )
                    }
                )
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
