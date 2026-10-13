"""Effect guard: every outward write happens once, or it waits in the park.

The worker proposes effects; the guard derives an idempotency key from run,
step and effect index (the model never has to remember one), records intent in
the journal, and holds the effect in an outbox until the step's gate passes.
On flush it dispatches with the key and records the result. After a crash it
reads back before any retry, re-sends only with the key, and parks anything
that has neither a key nor a read-back. Dispatch carries the lease epoch as a
fencing token so a receiver that understands it refuses a stale process.
"""

from __future__ import annotations

import hashlib
import json
import os
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Protocol

from .journal import Journal


def effect_key(run_id: str, step_index: int, effect_index: int) -> str:
    return hashlib.sha256(f"{run_id}:{step_index}:{effect_index}".encode()).hexdigest()[:32]


@dataclass(frozen=True)
class Fence:
    run_id: str
    epoch: int


class EffectAdapter(Protocol):
    kind: str
    keyed: bool          # the receiver deduplicates on our key
    readable: bool       # we can ask the receiver whether the key already landed
    irreversible: bool   # a mistake cannot be undone: needs a policy or a person

    def dispatch(self, key: str, payload: dict[str, Any], fence: Fence) -> Any: ...

    def read_back(self, key: str) -> Any | None: ...


class StaleFence(Exception):
    """The receiver has seen a newer epoch for this run and refused the write."""


class OutboxFileAdapter:
    """Drops one JSON file per effect into a directory. Keyed, readable and fenced.

    It stands in for any receiver that dedupes on a key and can be asked about
    it, and doubles as the test ledger for exactly-once.
    """

    kind = "outbox_file"
    keyed = True
    readable = True
    irreversible = False

    def __init__(self, directory: str):
        self.dir = directory
        os.makedirs(self.dir, exist_ok=True)

    def _fence_path(self, run_id: str) -> str:
        return os.path.join(self.dir, f".fence-{run_id}")

    def _check_fence(self, fence: Fence) -> None:
        path = self._fence_path(fence.run_id)
        seen = 0
        if os.path.exists(path):
            with open(path) as f:
                seen = int(f.read().strip() or 0)
        if fence.epoch < seen:
            raise StaleFence(f"epoch {fence.epoch} < {seen}")
        if fence.epoch > seen:
            tmp = f"{path}.{os.getpid()}"
            with open(tmp, "w") as f:
                f.write(str(fence.epoch))
            os.replace(tmp, path)

    def dispatch(self, key: str, payload: dict[str, Any], fence: Fence) -> Any:
        self._check_fence(fence)
        path = os.path.join(self.dir, f"{key}.json")
        body = json.dumps({"key": key, "payload": payload, "epoch": fence.epoch}, sort_keys=True).encode()
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        except FileExistsError:
            return {"path": path, "deduplicated": True}
        with os.fdopen(fd, "wb") as f:
            f.write(body)
            f.flush()
            os.fsync(f.fileno())
        # Every delivery attempt is logged so tests can count duplicates honestly.
        with open(os.path.join(self.dir, "deliveries.log"), "a") as log:
            log.write(key + "\n")
        return {"path": path, "deduplicated": False}

    def read_back(self, key: str) -> Any | None:
        path = os.path.join(self.dir, f"{key}.json")
        if os.path.exists(path):
            return {"path": path, "deduplicated": True}
        return None


class WebhookAdapter:
    """HTTP POST with an Idempotency-Key header. Keyed, not readable."""

    kind = "webhook"
    keyed = True
    readable = False
    irreversible = False

    def __init__(self, allowed_urls: list[str], timeout: float = 15.0):
        self.allowed = set(allowed_urls)
        self.timeout = timeout

    def dispatch(self, key: str, payload: dict[str, Any], fence: Fence) -> Any:
        url = payload["url"]
        if url not in self.allowed:
            raise PermissionError(f"webhook url not allowlisted: {url}")
        req = urllib.request.Request(
            url,
            data=json.dumps(payload.get("body", {})).encode(),
            headers={"Content-Type": "application/json", "Idempotency-Key": key,
                     "X-Fencing-Token": f"{fence.run_id}:{fence.epoch}"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:  # noqa: S310 (allowlisted)
            return {"status": resp.status}

    def read_back(self, key: str) -> Any | None:
        return None


class UnkeyedCommandAdapter:
    """A write with no key and no read-back. The guard never dispatches it unattended."""

    kind = "unkeyed"
    keyed = False
    readable = False
    irreversible = True

    def dispatch(self, key: str, payload: dict[str, Any], fence: Fence) -> Any:
        raise RuntimeError("unkeyed effects are only dispatched by a person")

    def read_back(self, key: str) -> Any | None:
        return None


@dataclass
class FlushResult:
    done: list[str] = field(default_factory=list)
    parked: list[tuple[str, str]] = field(default_factory=list)   # (key, reason)


class EffectGuard:
    def __init__(self, journal: Journal, adapters: list[EffectAdapter] | None = None):
        self.journal = journal
        self.adapters: dict[str, EffectAdapter] = {a.kind: a for a in (adapters or [])}

    def register(self, adapter: EffectAdapter) -> None:
        self.adapters[adapter.kind] = adapter

    def propose(self, run_id: str, epoch: int, step_index: int, effect_index: int, kind: str,
                payload: dict[str, Any]) -> str:
        key = effect_key(run_id, step_index, effect_index)
        self.journal.propose_effect(run_id, epoch, key, step_index, effect_index, kind, payload)
        return key

    def flush(self, run_id: str, epoch: int, step_index: int, approved: set[str] | None = None) -> FlushResult:
        """Dispatch this step's held effects. Call only after the step's gate passed."""
        approved = approved or set()
        result = FlushResult()
        fence = Fence(run_id, epoch)
        for eff in self.journal.effects(run_id, step_index):
            key, status = eff["key"], eff["status"]
            if status == "done":
                result.done.append(key)
                continue
            if status == "parked" and key not in approved:
                result.parked.append((key, "awaiting approval"))
                continue
            adapter = self.adapters.get(eff["kind"])
            if adapter is None:
                self.journal.mark_effect(run_id, epoch, key, "parked", {"reason": f"no adapter for {eff['kind']}"})
                result.parked.append((key, f"no adapter for {eff['kind']}"))
                continue
            if (adapter.irreversible or eff["payload"].get("irreversible")) and key not in approved:
                self.journal.mark_effect(run_id, epoch, key, "parked", {"reason": "irreversible"})
                result.parked.append((key, "irreversible effect needs approval"))
                continue
            if not adapter.keyed and not adapter.readable and key not in approved:
                self.journal.mark_effect(run_id, epoch, key, "parked", {"reason": "no key and no read-back"})
                result.parked.append((key, "no key and no read-back"))
                continue
            if status == "dispatching":
                # We crashed after recording intent. Look before any retry.
                if adapter.readable:
                    seen = adapter.read_back(key)
                    if seen is not None:
                        self.journal.mark_effect(run_id, epoch, key, "done", seen)
                        result.done.append(key)
                        continue
                if not adapter.keyed:
                    self.journal.mark_effect(run_id, epoch, key, "parked", {"reason": "in-flight, unverifiable"})
                    result.parked.append((key, "dispatch outcome unknown and receiver has no key"))
                    continue
            self.journal.mark_effect(run_id, epoch, key, "dispatching")
            try:
                out = adapter.dispatch(key, eff["payload"], fence)
            except StaleFence:
                raise
            except Exception as e:
                seen = adapter.read_back(key) if adapter.readable else None
                if seen is not None:
                    self.journal.mark_effect(run_id, epoch, key, "done", seen)
                    result.done.append(key)
                    continue
                self.journal.mark_effect(run_id, epoch, key, "parked", {"reason": f"dispatch failed: {e!r}"[:500]})
                result.parked.append((key, f"dispatch failed: {e!r}"[:200]))
                continue
            self.journal.mark_effect(run_id, epoch, key, "done", out)
            result.done.append(key)
        return result
