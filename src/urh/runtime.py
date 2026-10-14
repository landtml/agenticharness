"""Headless runtime: triggers fire runs, a bounded pool drives them, parks wake themselves.

One ``tick``:

1. **Cron triggers** that are due fire once. Missed slots (the runtime was down) coalesce into one run
   for the latest slot, with the count in its inputs. Each fire's run is created under the dedupe key
   ``trigger:<id>:<slot>`` *before* the trigger advances, so a crash between the two re-fires the same
   key and gets the same run back: a slot never makes two runs.
2. **Self-resolving parks** (outage cooldowns) are answered.
3. **Runnable runs** go to a thread pool, at most ``max_active_runs`` at a time and never one run twice.

Webhooks fire through ``fire_webhook``: the body must carry an HMAC-SHA256 signature made with the
trigger's secret, and the delivery id (or the body's hash) is the dedupe key, so a redelivered hook
returns the run it already made. The payload reaches models as untrusted input, never as instructions.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import logging
import threading
import time
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any

from .cron import Cron
from .notify import Notifier
from .orchestrator import Harness
from .signing import verify
from .spec import TaskSpec

log = logging.getLogger("urh.runtime")

MAX_PAYLOAD_CHARS = 64_000
MAX_COALESCE = 10_000


class WebhookRejected(Exception):
    def __init__(self, status: int, reason: str):
        super().__init__(reason)
        self.status = status


def _iso(ts: float) -> str:
    return dt.datetime.fromtimestamp(ts, dt.UTC).isoformat(timespec="seconds")


class Runtime:
    def __init__(
        self,
        harness: Harness,
        clock: Callable[[], float] = time.time,
        notifiers: list[Notifier] | None = None,
        notify_max_attempts: int = 8,
    ):
        self.h = harness
        self.notifiers = {n.name: n for n in notifiers or []}
        self.notify_max_attempts = notify_max_attempts
        self.journal = harness.journal
        self.clock = clock
        self._pool = ThreadPoolExecutor(
            max_workers=max(1, harness.config.max_active_runs), thread_name_prefix="urh-run"
        )
        self._inflight: dict[str, Future[str]] = {}
        self._lock = threading.Lock()
        self._stop = threading.Event()

    # ------------------------------------------------------------------ triggers
    def add_cron(self, name: str, schedule: str, spec: TaskSpec, budget_usd: float | None = None) -> str:
        cron = Cron.parse(schedule)
        first = cron.next_after(self.clock())
        return self.journal.add_trigger(
            name, "cron", spec.to_dict(), budget_usd or spec.budget_usd, schedule=schedule, next_fire_at=first
        )

    def add_webhook(self, name: str, spec: TaskSpec, secret: str, budget_usd: float | None = None) -> str:
        if len(secret) < 16:
            raise ValueError("webhook secret must be at least 16 characters")
        return self.journal.add_trigger(
            name, "webhook", spec.to_dict(), budget_usd or spec.budget_usd, secret=secret
        )

    def _submit(self, trig: dict[str, Any], dedupe: str, inputs: dict[str, Any]) -> str:
        spec = TaskSpec.from_dict({**trig["spec"], "inputs": {**trig["spec"].get("inputs", {}), **inputs}})
        return self.h.submit(spec, dedupe_key=dedupe, budget_usd=trig["budget_usd"])

    def fire_due(self) -> list[str]:
        now = self.clock()
        fired = []
        for trig in self.journal.due_triggers(now):
            try:
                cron = Cron.parse(trig["schedule"])
            except ValueError as e:
                log.error("trigger %s has a bad schedule: %s; disabling it", trig["name"], e)
                self.journal.set_trigger_enabled(trig["id"], False)
                continue
            slot, missed = trig["next_fire_at"], 0
            while missed < MAX_COALESCE:
                nxt = cron.next_after(slot)
                if nxt > now:
                    break
                slot, missed = nxt, missed + 1
            inputs = {"trigger": trig["name"], "fired_for": _iso(slot), "missed_slots": missed}
            run_id = self._submit(trig, f"trigger:{trig['id']}:{int(slot)}", inputs)
            if self.journal.advance_trigger(trig["id"], trig["next_fire_at"], cron.next_after(now)):
                fired.append(run_id)
        return fired

    def fire_webhook(
        self, name: str, body: bytes, signature: str | None, delivery: str | None = None
    ) -> tuple[str, bool]:
        """Returns (run_id, created). Raises WebhookRejected with an HTTP status."""
        trig = self.journal.get_trigger(name)
        if trig is None or trig["kind"] != "webhook":
            raise WebhookRejected(404, "no such webhook")
        if not trig["enabled"]:
            raise WebhookRejected(409, "webhook disabled")
        if not verify(trig["secret"], body, signature):
            raise WebhookRejected(401, "bad signature")
        text = body.decode("utf-8", errors="replace")
        try:
            payload: Any = json.loads(text)
        except json.JSONDecodeError:
            payload = text
        if len(json.dumps(payload, default=str)) > MAX_PAYLOAD_CHARS:
            raise WebhookRejected(413, "payload too large")
        key = delivery or hashlib.sha256(body).hexdigest()
        dedupe = f"hook:{trig['id']}:{key[:200]}"
        existing = self.journal.find_run_by_dedupe(dedupe)
        if existing is not None:
            return existing, False
        run_id = self._submit(trig, dedupe, {"trigger": name, "delivery": key[:200], "payload": payload})
        self.journal.advance_trigger(trig["id"], None, None)
        return run_id, True

    # ------------------------------------------------------------------ dispatch
    def _reap(self) -> None:
        with self._lock:
            for rid, fut in list(self._inflight.items()):
                if fut.done():
                    del self._inflight[rid]
                    if fut.exception() is not None:
                        log.error("run %s crashed", rid, exc_info=fut.exception())

    def dispatch(self) -> list[str]:
        self._reap()
        started = []
        with self._lock:
            for rid in self.h.runnable():
                if len(self._inflight) >= self.h.config.max_active_runs or self._stop.is_set():
                    break
                if rid in self._inflight:
                    continue
                self._inflight[rid] = self._pool.submit(self.h.run, rid)
                started.append(rid)
        return started

    # ------------------------------------------------------------------ notifications
    def notify_parks(self) -> list[str]:
        """Tell a person about every open park that will not wake itself. Returns the keys sent this call."""
        if not self.notifiers:
            return []
        parks = {p["id"]: p for p in self.journal.parks(status="open")}
        for park in parks.values():
            if park["preconditions"].get("wake_at") is None:
                for channel in self.notifiers:
                    self.journal.enqueue_notification(park["id"], channel)
        sent = []
        now = self.clock()
        for row in self.journal.due_notifications(now):
            park = parks.get(row["park_id"])
            notifier = self.notifiers.get(row["channel"])
            if park is None or notifier is None:  # answered meanwhile, or channel removed: nothing to say
                self.journal.mark_notification(row["key"], ok=False, error="obsolete", give_up=True)
                continue
            run = self.journal.get_run(park["run_id"])
            message = {
                "event": "park",
                "park_id": park["id"],
                "run_id": park["run_id"],
                "step_index": park["step_index"],
                "reason": park["reason"],
                "question": park["question"],
                "goal": run.spec.get("goal"),
            }
            try:
                notifier.send(row["key"], message)
            except Exception as e:  # any failure: retry with backoff, never block the runtime
                attempts = row["attempts"] + 1
                give_up = attempts >= self.notify_max_attempts
                self.journal.mark_notification(
                    row["key"],
                    ok=False,
                    error=repr(e),
                    retry_at=now + min(3600, 5 * 2**attempts),
                    give_up=give_up,
                )
                if give_up:
                    log.error("giving up notifying %s via %s: %r", park["id"], row["channel"], e)
                continue
            self.journal.mark_notification(row["key"], ok=True)
            sent.append(row["key"])
        return sent

    def tick(self) -> dict[str, list[str]]:
        fired = self.fire_due()
        woke = self.h.wake_due()
        started = self.dispatch()
        return {"fired": fired, "woke": woke, "started": started, "notified": self.notify_parks()}

    def inflight(self) -> list[str]:
        self._reap()
        with self._lock:
            return list(self._inflight)

    def serve(self, interval: float = 1.0) -> None:
        while not self._stop.is_set():
            try:
                self.tick()
            except Exception:  # one bad tick must not take the runtime down
                log.exception("tick failed")
            self._stop.wait(interval)

    def stop(self, wait: bool = True) -> None:
        """Stop starting work. Runs in flight finish their current step; a killed one resumes elsewhere."""
        self._stop.set()
        self._pool.shutdown(wait=wait, cancel_futures=True)

    def wait_idle(self, timeout: float = 60.0) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if not self.inflight():
                return True
            time.sleep(0.05)
        return False
