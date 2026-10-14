"""Headless sessions: a conversation of tasks over one evolving codebase.

A session holds a template (gate, constraints, facts, an optional starting ``seed_dir``) and an
ordered list of messages. Each message becomes its own durable run whose goal is the message and whose
starting tree is the previous run's last verified commit, so follow-ups build on what was verified,
never on half-finished work.

Ordering is strict. A message waits until the run before it is ``done`` or ``failed``; a parked
predecessor holds the session until someone answers it. Turning a message into a run uses the dedupe
key ``session:<id>:<seq>`` and only then binds the run to the message, so a crash between the two
finds the same run again: one message, one run.

A message may name the gate checks it adds (``checks``). A run is gated by every check named by its
message and the ones before it, so behaviour verified earlier keeps being checked, and a check meant
for a later message cannot fail an earlier one. If no message names any, every check applies.

Earlier messages and their outcomes go to the run as untrusted inputs. They are context for the
planner, not instructions; the instruction is the message itself.
"""

from __future__ import annotations

import os
import shutil
from typing import Any

from .checkpoint import GitCheckpoint
from .orchestrator import Harness
from .spec import TaskSpec

TERMINAL = ("done", "failed")
HISTORY = 10


def _gated(template: dict[str, Any], upto: list[dict[str, Any]]) -> dict[str, Any]:
    named = [c for m in upto if m["checks"] for c in m["checks"]]
    if not any(m["checks"] is not None for m in upto):
        return template
    gate = dict(template.get("gate", {}))
    gate["checks"] = [c for c in gate.get("checks", []) if c["name"] in set(named)]
    return {**template, "gate": gate}


class Sessions:
    def __init__(self, harness: Harness):
        self.h = harness
        self.j = harness.journal

    def create(self, title: str, template: dict[str, Any], budget_usd: float = 1.0) -> str:
        template = {k: v for k, v in template.items() if k not in ("goal", "inputs")}
        if template.get("steps"):
            raise ValueError("a session template cannot fix steps: each message is planned on its own")
        TaskSpec.from_dict({"goal": "-", **template})  # validate early
        return self.j.create_session(title, template, budget_usd)

    def send(self, session_id: str, text: str, checks: list[str] | None = None) -> int:
        text = text.strip()
        if not text:
            raise ValueError("message text is required")
        if checks is not None:
            session = self.j.get_session(session_id)
            if session is None:
                raise KeyError(session_id)
            known = {c["name"] for c in session["template"].get("gate", {}).get("checks", [])}
            unknown = sorted(set(checks) - known)
            if unknown:
                raise ValueError(f"no such gate checks: {', '.join(unknown)}")
        seq = self.j.add_session_message(session_id, text, checks)
        self.advance()
        return seq

    def _seed(self, session: dict[str, Any], prev_run_id: str | None, seq: int) -> str | None:
        """The starting tree for message ``seq``: the previous run's verified commit, written to disk once."""
        if prev_run_id is None:
            return session["template"].get("seed_dir")
        prev = self.j.get_run(prev_run_id)
        if prev.verified_commit is None:  # the previous run verified nothing: start where it started
            return prev.spec.get("seed_dir")
        dest = os.path.join(self.h.home, "sessions", session["id"], f"seed-{seq:04d}")
        if not os.path.isdir(dest):
            tmp = dest + ".tmp"
            shutil.rmtree(tmp, ignore_errors=True)
            GitCheckpoint(os.path.join(self.h.home, "runs", prev_run_id)).export(prev.verified_commit, tmp)
            os.replace(tmp, dest)  # atomic: a crash leaves either nothing or the whole tree
        return dest

    def advance(self) -> list[str]:
        """Turn every message whose predecessor has finished into a run. Returns the new run ids."""
        started = []
        for msg in self.j.pending_session_messages():
            sid, seq = msg["session_id"], msg["seq"]
            history = self.j.session_messages(sid)
            prev = next((m for m in history if m["seq"] == seq - 1), None)
            if prev is not None and (
                prev["run_id"] is None or self.j.get_run(prev["run_id"]).status not in TERMINAL
            ):
                continue  # still working, or parked: this message waits its turn
            session = self.j.get_session(sid)
            assert session is not None
            earlier = [
                {"seq": m["seq"], "message": m["text"], "outcome": self.j.get_run(m["run_id"]).status}
                for m in history
                if m["seq"] < seq and m["run_id"]
            ][-HISTORY:]
            spec = TaskSpec.from_dict(
                {
                    **_gated(session["template"], [m for m in history if m["seq"] <= seq]),
                    "goal": msg["text"],
                    "seed_dir": self._seed(session, prev["run_id"] if prev else None, seq),
                    "inputs": {
                        "session": sid,
                        "title": session["title"],
                        "message_seq": seq,
                        "earlier": earlier,
                    },
                }
            )
            run_id = self.h.submit(spec, dedupe_key=f"session:{sid}:{seq}", budget_usd=session["budget_usd"])
            self.j.bind_session_message(sid, seq, run_id)
            started.append(run_id)
        return started

    def view(self, session_id: str) -> dict[str, Any]:
        session = self.j.get_session(session_id)
        if session is None:
            raise KeyError(session_id)
        messages = []
        for m in self.j.session_messages(session_id):
            item: dict[str, Any] = {
                "seq": m["seq"],
                "text": m["text"],
                "checks": m["checks"],
                "run_id": m["run_id"],
                "status": "waiting",
            }
            if m["run_id"]:
                run = self.j.get_run(m["run_id"])
                item.update(
                    status=run.status, spent_usd=round(run.spent_usd, 6), verified_commit=run.verified_commit
                )
            messages.append(item)
        return {
            "id": session["id"],
            "title": session["title"],
            "budget_usd": session["budget_usd"],
            "messages": messages,
        }

    def files(self, session_id: str) -> dict[str, str]:
        """The session's current verified tree: the latest run that verified anything."""
        for m in reversed(self.j.session_messages(session_id)):
            if m["run_id"]:
                run = self.j.get_run(m["run_id"])
                if run.verified_commit:
                    ckpt = GitCheckpoint(os.path.join(self.h.home, "runs", run.id))
                    names = ckpt._git("ls-tree", "-r", "--name-only", run.verified_commit).decode().split()
                    return {
                        n: ckpt._git("show", f"{run.verified_commit}:{n}").decode(errors="replace")
                        for n in names
                    }
        return {}
