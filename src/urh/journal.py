"""Durable journal: the only state that outlives a step.

One SQLite file (WAL mode) holds run state, version pins, leases, the budget,
step attempts, gate verdicts, effects with their keys, parks and the model-call
log. Everything is written before the run moves on. Writes that belong to a run
are fenced by the lease epoch, so a process that lost its lease cannot move the
run any further.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

SCHEMA_VERSION = 2

_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS runs (
    id              TEXT PRIMARY KEY,
    dedupe_key      TEXT UNIQUE,
    spec_json       TEXT NOT NULL,
    pins_json       TEXT NOT NULL,
    status          TEXT NOT NULL,          -- queued | running | parked | done | failed
    status_reason   TEXT,
    budget_usd      REAL NOT NULL,
    spent_usd       REAL NOT NULL DEFAULT 0,
    reserved_usd    REAL NOT NULL DEFAULT 0,
    denials         INTEGER NOT NULL DEFAULT 0,
    step_index      INTEGER NOT NULL DEFAULT 0,
    verified_commit TEXT,
    lease_owner     TEXT,
    lease_epoch     INTEGER NOT NULL DEFAULT 0,
    lease_expires   REAL NOT NULL DEFAULT 0,
    created_at      REAL NOT NULL,
    updated_at      REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
    seq     INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id  TEXT NOT NULL,
    ts      REAL NOT NULL,
    epoch   INTEGER NOT NULL,
    kind    TEXT NOT NULL,
    data    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS events_run ON events(run_id, seq);
CREATE TABLE IF NOT EXISTS step_plans (
    run_id     TEXT NOT NULL,
    step_index INTEGER NOT NULL,
    step_json  TEXT NOT NULL,
    source     TEXT NOT NULL,                -- spec | manager
    PRIMARY KEY (run_id, step_index)
);
CREATE TABLE IF NOT EXISTS attempts (
    run_id      TEXT NOT NULL,
    step_index  INTEGER NOT NULL,
    attempt     INTEGER NOT NULL,
    epoch       INTEGER NOT NULL,
    status      TEXT NOT NULL,               -- running | pass | fail | unsure | aborted
    tree        TEXT,
    commit_sha  TEXT,
    verdict     TEXT,
    started_at  REAL NOT NULL,
    ended_at    REAL,
    PRIMARY KEY (run_id, step_index, attempt)
);
CREATE TABLE IF NOT EXISTS model_calls (
    id              TEXT PRIMARY KEY,
    run_id          TEXT NOT NULL,
    step_index      INTEGER NOT NULL,
    attempt         INTEGER NOT NULL,
    call_index      INTEGER NOT NULL,
    role            TEXT NOT NULL,           -- worker | manager | judge | escalation
    provider        TEXT NOT NULL,
    model           TEXT NOT NULL,
    status          TEXT NOT NULL,           -- reserved | ok | error
    reserved_usd    REAL NOT NULL,
    cost_usd        REAL,
    input_tokens    INTEGER,
    output_tokens   INTEGER,
    cache_read      INTEGER,
    cache_write     INTEGER,
    latency_ms      INTEGER,
    stop_reason     TEXT,
    request_blob    TEXT,
    response_blob   TEXT,
    error           TEXT,
    ts              REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS model_calls_run ON model_calls(run_id, step_index, attempt, call_index);
CREATE TABLE IF NOT EXISTS effects (
    key          TEXT PRIMARY KEY,
    run_id       TEXT NOT NULL,
    step_index   INTEGER NOT NULL,
    effect_index INTEGER NOT NULL,
    kind         TEXT NOT NULL,
    payload      TEXT NOT NULL,
    status       TEXT NOT NULL,              -- proposed | dispatching | done | failed | parked
    result       TEXT,
    epoch        INTEGER NOT NULL,
    created_at   REAL NOT NULL,
    updated_at   REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS parks (
    id            TEXT PRIMARY KEY,
    run_id        TEXT NOT NULL,
    step_index    INTEGER NOT NULL,
    reason        TEXT NOT NULL,
    question      TEXT NOT NULL,
    preconditions TEXT NOT NULL,
    status        TEXT NOT NULL,             -- open | answered | claimed | void
    answer        TEXT,
    claimed_by    TEXT,
    created_at    REAL NOT NULL,
    updated_at    REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS triggers (
    id            TEXT PRIMARY KEY,
    name          TEXT NOT NULL UNIQUE,
    kind          TEXT NOT NULL,             -- cron | webhook
    schedule      TEXT,                      -- cron expression (cron triggers)
    spec_json     TEXT NOT NULL,             -- the run template
    budget_usd    REAL NOT NULL,
    secret        TEXT,                      -- HMAC key (webhook triggers)
    enabled       INTEGER NOT NULL DEFAULT 1,
    next_fire_at  REAL,
    last_fired_at REAL,
    fired         INTEGER NOT NULL DEFAULT 0,
    created_at    REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
    id            TEXT PRIMARY KEY,
    title         TEXT NOT NULL,
    template_json TEXT NOT NULL,             -- spec fields every message's run inherits (gate, constraints...)
    budget_usd    REAL NOT NULL,             -- per message
    created_at    REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS session_messages (
    session_id    TEXT NOT NULL,
    seq           INTEGER NOT NULL,
    text          TEXT NOT NULL,
    run_id        TEXT,                      -- NULL until the previous message's run has finished
    created_at    REAL NOT NULL,
    PRIMARY KEY (session_id, seq)
);
CREATE TABLE IF NOT EXISTS notifications (
    key           TEXT PRIMARY KEY,          -- <park_id>:<channel>; also the receiver's Idempotency-Key
    park_id       TEXT NOT NULL,
    channel       TEXT NOT NULL,
    status        TEXT NOT NULL,             -- pending | sent | failed
    attempts      INTEGER NOT NULL DEFAULT 0,
    next_try_at   REAL NOT NULL,
    last_error    TEXT,
    created_at    REAL NOT NULL,
    sent_at       REAL
);
"""


class LeaseLost(Exception):
    """This process no longer holds the run's lease; it must stop touching the run."""


class BudgetExceeded(Exception):
    """A reservation would push the run past its global budget."""


@dataclass
class Run:
    id: str
    dedupe_key: str | None
    spec: dict[str, Any]
    pins: dict[str, Any]
    status: str
    status_reason: str | None
    budget_usd: float
    spent_usd: float
    reserved_usd: float
    denials: int
    step_index: int
    verified_commit: str | None
    lease_owner: str | None
    lease_epoch: int
    lease_expires: float

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> Run:
        return cls(
            id=row["id"],
            dedupe_key=row["dedupe_key"],
            spec=json.loads(row["spec_json"]),
            pins=json.loads(row["pins_json"]),
            status=row["status"],
            status_reason=row["status_reason"],
            budget_usd=row["budget_usd"],
            spent_usd=row["spent_usd"],
            reserved_usd=row["reserved_usd"],
            denials=row["denials"],
            step_index=row["step_index"],
            verified_commit=row["verified_commit"],
            lease_owner=row["lease_owner"],
            lease_epoch=row["lease_epoch"],
            lease_expires=row["lease_expires"],
        )


def _now() -> float:
    return time.time()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


class Journal:
    """Thread-safe facade over the SQLite journal.

    Each public method is one transaction. Methods that change a run take the
    caller's lease ``epoch`` and raise :class:`LeaseLost` when it is stale.
    """

    def __init__(self, path: str | os.PathLike[str]):
        self.path = os.fspath(path)
        os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
        self._lock = threading.RLock()
        # One connection per thread: a shared connection lets concurrent readers interleave on its
        # cursor and read each other's rows. Writers still serialize (in-process lock + BEGIN IMMEDIATE).
        self._local = threading.local()
        self._all: list[sqlite3.Connection] = []
        self._closed = False
        self._migrate()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=30, isolation_level=None, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=FULL")
        conn.execute("PRAGMA busy_timeout=30000")
        return conn

    @property
    def _conn(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            if self._closed:
                raise sqlite3.ProgrammingError("journal is closed")
            conn = self._local.conn = self._connect()
            with self._lock:
                self._all.append(conn)
        return conn

    # ------------------------------------------------------------------ plumbing
    @contextmanager
    def tx(self) -> Iterator[sqlite3.Connection]:
        """BEGIN IMMEDIATE so concurrent writers serialize instead of failing late."""
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                yield self._conn
            except BaseException:
                self._conn.execute("ROLLBACK")
                raise
            else:
                self._conn.execute("COMMIT")

    def _migrate(self) -> None:
        with self._lock:
            # executescript commits on its own; the DDL is idempotent, so run it bare.
            self._conn.executescript(_SCHEMA)
        with self.tx() as c:
            row = c.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
            if row is None:
                c.execute("INSERT INTO meta(key, value) VALUES ('schema_version', ?)", (str(SCHEMA_VERSION),))
            elif int(row["value"]) > SCHEMA_VERSION:
                raise RuntimeError(
                    f"journal schema {row['value']} is newer than this harness ({SCHEMA_VERSION}); refusing to open"
                )
            elif int(row["value"]) < SCHEMA_VERSION:
                # 1 -> 2 only added the triggers table, which the idempotent DDL above created.
                c.execute("UPDATE meta SET value=? WHERE key='schema_version'", (str(SCHEMA_VERSION),))

    def close(self) -> None:
        with self._lock:
            self._closed = True
            for conn in self._all:
                conn.close()
            self._all.clear()

    def schema_version(self) -> int:
        row = self._conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
        return int(row["value"])

    @staticmethod
    def _check_fence(c: sqlite3.Connection, run_id: str, epoch: int) -> None:
        row = c.execute("SELECT lease_epoch FROM runs WHERE id=?", (run_id,)).fetchone()
        if row is None:
            raise KeyError(run_id)
        if row["lease_epoch"] != epoch:
            raise LeaseLost(f"run {run_id}: epoch {epoch} superseded by {row['lease_epoch']}")

    def _event(self, c: sqlite3.Connection, run_id: str, epoch: int, kind: str, data: dict[str, Any]) -> None:
        c.execute(
            "INSERT INTO events(run_id, ts, epoch, kind, data) VALUES (?,?,?,?,?)",
            (run_id, _now(), epoch, kind, json.dumps(data, sort_keys=True)),
        )

    def event(self, run_id: str, epoch: int, kind: str, **data: Any) -> None:
        with self.tx() as c:
            self._check_fence(c, run_id, epoch)
            self._event(c, run_id, epoch, kind, data)

    def events(self, run_id: str) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT seq, ts, epoch, kind, data FROM events WHERE run_id=? ORDER BY seq", (run_id,)
        ).fetchall()
        return [
            {"seq": r["seq"], "ts": r["ts"], "epoch": r["epoch"], "kind": r["kind"], **json.loads(r["data"])}
            for r in rows
        ]

    # ------------------------------------------------------------------ runs
    def create_run(
        self,
        spec: dict[str, Any],
        pins: dict[str, Any],
        budget_usd: float,
        dedupe_key: str | None = None,
    ) -> tuple[str, bool]:
        """Create a run, or return the existing one for this dedupe key. Returns (run_id, created)."""
        with self.tx() as c:
            if dedupe_key is not None:
                row = c.execute("SELECT id FROM runs WHERE dedupe_key=?", (dedupe_key,)).fetchone()
                if row is not None:
                    return row["id"], False
            run_id = new_id("run")
            ts = _now()
            c.execute(
                "INSERT INTO runs(id, dedupe_key, spec_json, pins_json, status, budget_usd, created_at, updated_at)"
                " VALUES (?,?,?,?,?,?,?,?)",
                (
                    run_id,
                    dedupe_key,
                    json.dumps(spec, sort_keys=True),
                    json.dumps(pins, sort_keys=True),
                    "queued",
                    budget_usd,
                    ts,
                    ts,
                ),
            )
            self._event(
                c,
                run_id,
                0,
                "run_created",
                {"dedupe_key": dedupe_key, "budget_usd": budget_usd, "pins": pins},
            )
            return run_id, True

    def get_run(self, run_id: str) -> Run:
        row = self._conn.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
        if row is None:
            raise KeyError(run_id)
        return Run.from_row(row)

    def list_runs(self, status: str | None = None) -> list[Run]:
        if status is None:
            rows = self._conn.execute("SELECT * FROM runs ORDER BY created_at").fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM runs WHERE status=? ORDER BY created_at", (status,)
            ).fetchall()
        return [Run.from_row(r) for r in rows]

    def count_active(self) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) AS n FROM runs WHERE status='running' AND lease_expires > ?", (_now(),)
        ).fetchone()
        return int(row["n"])

    def total_spent(self) -> float:
        row = self._conn.execute(
            "SELECT COALESCE(SUM(spent_usd + reserved_usd), 0) AS s FROM runs"
        ).fetchone()
        return float(row["s"])

    def set_status(self, run_id: str, epoch: int, status: str, reason: str | None = None) -> None:
        with self.tx() as c:
            self._check_fence(c, run_id, epoch)
            c.execute(
                "UPDATE runs SET status=?, status_reason=?, updated_at=? WHERE id=?",
                (status, reason, _now(), run_id),
            )
            self._event(c, run_id, epoch, "status", {"status": status, "reason": reason})

    def requeue(self, run_id: str) -> None:
        """Move a parked run back to queued (used when its park is answered)."""
        with self.tx() as c:
            c.execute(
                "UPDATE runs SET status='queued', status_reason=NULL, updated_at=? WHERE id=? AND status='parked'",
                (_now(), run_id),
            )

    # ------------------------------------------------------------------ leases
    def acquire_lease(self, run_id: str, owner: str, ttl: float) -> int | None:
        """Take the run's lease if it is free, expired, or already ours. Returns the new epoch.

        Every acquisition bumps the epoch, so any earlier holder is fenced out
        even if it is still alive.
        """
        with self.tx() as c:
            row = c.execute(
                "SELECT lease_owner, lease_expires, status FROM runs WHERE id=?", (run_id,)
            ).fetchone()
            if row is None:
                raise KeyError(run_id)
            if row["status"] in ("done", "failed"):
                return None
            now = _now()
            if row["lease_owner"] not in (None, owner) and row["lease_expires"] > now:
                return None
            c.execute(
                "UPDATE runs SET lease_owner=?, lease_epoch=lease_epoch+1, lease_expires=?, updated_at=? WHERE id=?",
                (owner, now + ttl, now, run_id),
            )
            epoch = c.execute("SELECT lease_epoch FROM runs WHERE id=?", (run_id,)).fetchone()["lease_epoch"]
            self._event(
                c, run_id, epoch, "lease_acquired", {"owner": owner, "previous_owner": row["lease_owner"]}
            )
            return int(epoch)

    def renew_lease(self, run_id: str, epoch: int, ttl: float) -> None:
        with self.tx() as c:
            self._check_fence(c, run_id, epoch)
            c.execute("UPDATE runs SET lease_expires=? WHERE id=?", (_now() + ttl, run_id))

    def release_lease(self, run_id: str, epoch: int) -> None:
        with self.tx() as c:
            try:
                self._check_fence(c, run_id, epoch)
            except LeaseLost:
                return
            c.execute("UPDATE runs SET lease_owner=NULL, lease_expires=0 WHERE id=?", (run_id,))
            self._event(c, run_id, epoch, "lease_released", {})

    # ------------------------------------------------------------------ steps
    def plan_step(
        self, run_id: str, epoch: int, step_index: int, step: dict[str, Any], source: str
    ) -> dict[str, Any]:
        """Record the decision of what step N is. First writer wins, so a resume reuses it."""
        with self.tx() as c:
            self._check_fence(c, run_id, epoch)
            row = c.execute(
                "SELECT step_json FROM step_plans WHERE run_id=? AND step_index=?", (run_id, step_index)
            ).fetchone()
            if row is not None:
                return json.loads(row["step_json"])
            c.execute(
                "INSERT INTO step_plans(run_id, step_index, step_json, source) VALUES (?,?,?,?)",
                (run_id, step_index, json.dumps(step, sort_keys=True), source),
            )
            self._event(
                c, run_id, epoch, "step_planned", {"step_index": step_index, "source": source, "step": step}
            )
            return step

    def replan_step(
        self, run_id: str, epoch: int, step_index: int, step: dict[str, Any], source: str
    ) -> dict[str, Any]:
        """Replace the not-yet-verified step N after its repairs ran out. Its failed attempts stop counting
        toward the new step's repair limit; they stay in the journal as ``superseded``."""
        with self.tx() as c:
            self._check_fence(c, run_id, epoch)
            row = c.execute("SELECT step_index FROM runs WHERE id=?", (run_id,)).fetchone()
            if row["step_index"] != step_index:
                raise RuntimeError(f"run {run_id} is at step {row['step_index']}, cannot replan {step_index}")
            c.execute(
                "UPDATE step_plans SET step_json=?, source=? WHERE run_id=? AND step_index=?",
                (json.dumps(step, sort_keys=True), source, run_id, step_index),
            )
            c.execute(
                "UPDATE attempts SET status='superseded' WHERE run_id=? AND step_index=?"
                " AND status IN ('fail', 'unsure', 'aborted')",
                (run_id, step_index),
            )
            self._event(
                c, run_id, epoch, "step_replanned", {"step_index": step_index, "source": source, "step": step}
            )
            return step

    def planned_step(self, run_id: str, step_index: int) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT step_json FROM step_plans WHERE run_id=? AND step_index=?", (run_id, step_index)
        ).fetchone()
        return None if row is None else json.loads(row["step_json"])

    def begin_attempt(self, run_id: str, epoch: int, step_index: int) -> int:
        with self.tx() as c:
            self._check_fence(c, run_id, epoch)
            # An attempt left 'running' by a dead process is aborted, not resumed (D1).
            c.execute(
                "UPDATE attempts SET status='aborted', ended_at=? WHERE run_id=? AND step_index=? AND status='running'",
                (_now(), run_id, step_index),
            )
            row = c.execute(
                "SELECT COALESCE(MAX(attempt), 0) AS a FROM attempts WHERE run_id=? AND step_index=?",
                (run_id, step_index),
            ).fetchone()
            attempt = int(row["a"]) + 1
            c.execute(
                "INSERT INTO attempts(run_id, step_index, attempt, epoch, status, started_at) VALUES (?,?,?,?,?,?)",
                (run_id, step_index, attempt, epoch, "running", _now()),
            )
            c.execute("UPDATE runs SET status='running', updated_at=? WHERE id=?", (_now(), run_id))
            self._event(c, run_id, epoch, "attempt_started", {"step_index": step_index, "attempt": attempt})
            return attempt

    def attempts(self, run_id: str, step_index: int | None = None) -> list[dict[str, Any]]:
        if step_index is None:
            rows = self._conn.execute(
                "SELECT * FROM attempts WHERE run_id=? ORDER BY step_index, attempt", (run_id,)
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM attempts WHERE run_id=? AND step_index=? ORDER BY attempt",
                (run_id, step_index),
            ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["verdict"] = json.loads(d["verdict"]) if d["verdict"] else None
            out.append(d)
        return out

    def record_verdict(
        self,
        run_id: str,
        epoch: int,
        step_index: int,
        attempt: int,
        status: str,
        tree: str | None,
        commit_sha: str | None,
        verdict: dict[str, Any],
    ) -> None:
        with self.tx() as c:
            self._check_fence(c, run_id, epoch)
            c.execute(
                "UPDATE attempts SET status=?, tree=?, commit_sha=?, verdict=?, ended_at=?"
                " WHERE run_id=? AND step_index=? AND attempt=?",
                (
                    status,
                    tree,
                    commit_sha,
                    json.dumps(verdict, sort_keys=True),
                    _now(),
                    run_id,
                    step_index,
                    attempt,
                ),
            )
            self._event(
                c,
                run_id,
                epoch,
                "verdict",
                {
                    "step_index": step_index,
                    "attempt": attempt,
                    "status": status,
                    "tree": tree,
                    "commit": commit_sha,
                    "summary": verdict.get("summary"),
                },
            )

    def complete_step(self, run_id: str, epoch: int, step_index: int, commit_sha: str) -> None:
        """Advance the run past a verified step. This is the checkpoint a resume starts from."""
        with self.tx() as c:
            self._check_fence(c, run_id, epoch)
            row = c.execute("SELECT step_index FROM runs WHERE id=?", (run_id,)).fetchone()
            if row["step_index"] != step_index:
                raise RuntimeError(f"run {run_id} is at step {row['step_index']}, not {step_index}")
            c.execute(
                "UPDATE runs SET step_index=?, verified_commit=?, updated_at=? WHERE id=?",
                (step_index + 1, commit_sha, _now(), run_id),
            )
            self._event(c, run_id, epoch, "step_completed", {"step_index": step_index, "commit": commit_sha})

    def set_verified_commit(self, run_id: str, epoch: int, commit_sha: str) -> None:
        with self.tx() as c:
            self._check_fence(c, run_id, epoch)
            c.execute(
                "UPDATE runs SET verified_commit=?, updated_at=? WHERE id=?", (commit_sha, _now(), run_id)
            )

    # ------------------------------------------------------------------ budget
    def reserve(
        self,
        run_id: str,
        epoch: int,
        call: dict[str, Any],
        amount: float,
    ) -> str:
        """Reserve ``amount`` against the run's one global budget and log the call as in flight."""
        with self.tx() as c:
            self._check_fence(c, run_id, epoch)
            row = c.execute(
                "SELECT budget_usd, spent_usd, reserved_usd FROM runs WHERE id=?", (run_id,)
            ).fetchone()
            if row["spent_usd"] + row["reserved_usd"] + amount > row["budget_usd"] + 1e-12:
                c.execute("UPDATE runs SET denials=denials+1 WHERE id=?", (run_id,))
                self._event(
                    c, run_id, epoch, "budget_denied", {"amount": amount, **{k: row[k] for k in row.keys()}}
                )
                denied = (
                    f"run {run_id}: reserving ${amount:.4f} exceeds budget "
                    f"(spent ${row['spent_usd']:.4f} + reserved ${row['reserved_usd']:.4f} of ${row['budget_usd']:.4f})"
                )
                call_id = ""
            else:
                denied = None
                call_id = self._reserve_row(c, run_id, call, amount)
        if denied is not None:
            # Raised after the commit so the denial itself stays on the record.
            raise BudgetExceeded(denied)
        return call_id

    def _reserve_row(self, c: sqlite3.Connection, run_id: str, call: dict[str, Any], amount: float) -> str:
        call_id = new_id("call")
        c.execute("UPDATE runs SET reserved_usd=reserved_usd+? WHERE id=?", (amount, run_id))
        c.execute(
            "INSERT INTO model_calls(id, run_id, step_index, attempt, call_index, role, provider, model, status,"
            " reserved_usd, request_blob, ts) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                call_id,
                run_id,
                call["step_index"],
                call["attempt"],
                call["call_index"],
                call["role"],
                call["provider"],
                call["model"],
                "reserved",
                amount,
                call.get("request_blob"),
                _now(),
            ),
        )
        return call_id

    def settle(self, call_id: str, cost_usd: float, fields: dict[str, Any], status: str = "ok") -> None:
        """Replace a reservation with the actual cost. Not fenced: money spent is spent."""
        allowed = {
            "input_tokens",
            "output_tokens",
            "cache_read",
            "cache_write",
            "latency_ms",
            "stop_reason",
            "response_blob",
            "error",
        }
        cols = {k: v for k, v in fields.items() if k in allowed}
        with self.tx() as c:
            row = c.execute(
                "SELECT run_id, reserved_usd, status FROM model_calls WHERE id=?", (call_id,)
            ).fetchone()
            if row is None or row["status"] != "reserved":
                return
            c.execute(
                "UPDATE runs SET reserved_usd=MAX(0, reserved_usd-?), spent_usd=spent_usd+? WHERE id=?",
                (row["reserved_usd"], cost_usd, row["run_id"]),
            )
            sets = ", ".join(f"{k}=?" for k in cols)
            c.execute(
                f"UPDATE model_calls SET status=?, cost_usd=?{', ' + sets if sets else ''} WHERE id=?",
                (status, cost_usd, *cols.values(), call_id),
            )

    def release_stale_reservations(self, run_id: str, epoch: int) -> float:
        """On resume: calls left 'reserved' by a dead process are written off at their reservation.

        We cannot know whether the provider billed them, so we charge the
        reservation (the upper bound) rather than pretend they were free.
        """
        with self.tx() as c:
            self._check_fence(c, run_id, epoch)
            rows = c.execute(
                "SELECT id, reserved_usd FROM model_calls WHERE run_id=? AND status='reserved'", (run_id,)
            ).fetchall()
            total = 0.0
            for r in rows:
                total += r["reserved_usd"]
                c.execute(
                    "UPDATE model_calls SET status='lost', cost_usd=reserved_usd WHERE id=?", (r["id"],)
                )
            if rows:
                c.execute(
                    "UPDATE runs SET reserved_usd=MAX(0, reserved_usd-?), spent_usd=spent_usd+? WHERE id=?",
                    (total, total, run_id),
                )
                self._event(c, run_id, epoch, "reservations_written_off", {"calls": len(rows), "usd": total})
            return total

    def add_budget(self, run_id: str, amount: float) -> None:
        with self.tx() as c:
            c.execute("UPDATE runs SET budget_usd=budget_usd+? WHERE id=?", (amount, run_id))
            self._event(c, run_id, 0, "budget_added", {"amount": amount})

    def model_calls(self, run_id: str) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM model_calls WHERE run_id=? ORDER BY ts, step_index, attempt, call_index", (run_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------ effects
    def propose_effect(
        self,
        run_id: str,
        epoch: int,
        key: str,
        step_index: int,
        effect_index: int,
        kind: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Record an effect's intent. Same key twice returns the first record unchanged."""
        with self.tx() as c:
            self._check_fence(c, run_id, epoch)
            row = c.execute("SELECT * FROM effects WHERE key=?", (key,)).fetchone()
            if row is not None:
                return dict(row)
            ts = _now()
            c.execute(
                "INSERT INTO effects(key, run_id, step_index, effect_index, kind, payload, status, epoch, created_at,"
                " updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    key,
                    run_id,
                    step_index,
                    effect_index,
                    kind,
                    json.dumps(payload, sort_keys=True),
                    "proposed",
                    epoch,
                    ts,
                    ts,
                ),
            )
            self._event(
                c, run_id, epoch, "effect_proposed", {"key": key, "kind": kind, "step_index": step_index}
            )
            return dict(c.execute("SELECT * FROM effects WHERE key=?", (key,)).fetchone())

    def mark_effect(self, run_id: str, epoch: int, key: str, status: str, result: Any = None) -> None:
        with self.tx() as c:
            self._check_fence(c, run_id, epoch)
            c.execute(
                "UPDATE effects SET status=?, result=?, epoch=?, updated_at=? WHERE key=?",
                (status, None if result is None else json.dumps(result, sort_keys=True), epoch, _now(), key),
            )
            self._event(c, run_id, epoch, f"effect_{status}", {"key": key})

    def discard_proposed_effects(self, run_id: str, epoch: int, step_index: int) -> int:
        """Drop effects a failed attempt proposed. They were never dispatched, so this is safe."""
        with self.tx() as c:
            self._check_fence(c, run_id, epoch)
            cur = c.execute(
                "DELETE FROM effects WHERE run_id=? AND step_index=? AND status='proposed'",
                (run_id, step_index),
            )
            if cur.rowcount:
                self._event(
                    c, run_id, epoch, "effects_discarded", {"step_index": step_index, "count": cur.rowcount}
                )
            return cur.rowcount

    def effects(self, run_id: str, step_index: int | None = None) -> list[dict[str, Any]]:
        if step_index is None:
            rows = self._conn.execute(
                "SELECT * FROM effects WHERE run_id=? ORDER BY step_index, effect_index", (run_id,)
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM effects WHERE run_id=? AND step_index=? ORDER BY effect_index",
                (run_id, step_index),
            ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["payload"] = json.loads(d["payload"])
            d["result"] = json.loads(d["result"]) if d["result"] else None
            out.append(d)
        return out

    # ------------------------------------------------------------------ parks
    def park(
        self,
        run_id: str,
        epoch: int,
        step_index: int,
        reason: str,
        question: str,
        preconditions: dict[str, Any] | None = None,
    ) -> str:
        with self.tx() as c:
            self._check_fence(c, run_id, epoch)
            park_id = new_id("park")
            ts = _now()
            c.execute(
                "INSERT INTO parks(id, run_id, step_index, reason, question, preconditions, status, created_at,"
                " updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    park_id,
                    run_id,
                    step_index,
                    reason,
                    question,
                    json.dumps(preconditions or {}, sort_keys=True),
                    "open",
                    ts,
                    ts,
                ),
            )
            c.execute(
                "UPDATE runs SET status='parked', status_reason=?, lease_owner=NULL, lease_expires=0, updated_at=?"
                " WHERE id=?",
                (reason, ts, run_id),
            )
            self._event(
                c, run_id, epoch, "parked", {"park_id": park_id, "reason": reason, "question": question}
            )
            return park_id

    def answer_park(self, park_id: str, answer: str) -> str:
        """A person answers a parked question. Returns the run id. The run is requeued."""
        with self.tx() as c:
            row = c.execute("SELECT run_id, status FROM parks WHERE id=?", (park_id,)).fetchone()
            if row is None:
                raise KeyError(park_id)
            if row["status"] != "open":
                raise ValueError(f"park {park_id} is {row['status']}, not open")
            c.execute(
                "UPDATE parks SET status='answered', answer=?, updated_at=? WHERE id=?",
                (answer, _now(), park_id),
            )
            c.execute(
                "UPDATE runs SET status='queued', status_reason=NULL, updated_at=? WHERE id=? AND status='parked'",
                (_now(), row["run_id"]),
            )
            self._event(c, row["run_id"], 0, "park_answered", {"park_id": park_id})
            return row["run_id"]

    def claim_answers(self, run_id: str, epoch: int, owner: str) -> list[dict[str, Any]]:
        """Claim every answered park of this run exactly once. A losing racer gets nothing."""
        with self.tx() as c:
            self._check_fence(c, run_id, epoch)
            rows = c.execute(
                "SELECT * FROM parks WHERE run_id=? AND status='answered' ORDER BY created_at", (run_id,)
            ).fetchall()
            claimed = []
            for r in rows:
                cur = c.execute(
                    "UPDATE parks SET status='claimed', claimed_by=?, updated_at=? WHERE id=? AND status='answered'",
                    (owner, _now(), r["id"]),
                )
                if cur.rowcount == 1:
                    d = dict(r)
                    d["preconditions"] = json.loads(d["preconditions"])
                    claimed.append(d)
                    self._event(c, run_id, epoch, "park_claimed", {"park_id": r["id"], "owner": owner})
            return claimed

    def parks(self, run_id: str | None = None, status: str | None = None) -> list[dict[str, Any]]:
        q = "SELECT * FROM parks WHERE 1=1"
        args: list[Any] = []
        if run_id is not None:
            q += " AND run_id=?"
            args.append(run_id)
        if status is not None:
            q += " AND status=?"
            args.append(status)
        rows = self._conn.execute(q + " ORDER BY created_at", args).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["preconditions"] = json.loads(d["preconditions"])
            out.append(d)
        return out

    # ------------------------------------------------------------------ triggers
    def add_trigger(
        self,
        name: str,
        kind: str,
        spec: dict[str, Any],
        budget_usd: float,
        schedule: str | None = None,
        secret: str | None = None,
        next_fire_at: float | None = None,
    ) -> str:
        if kind not in ("cron", "webhook"):
            raise ValueError(f"unknown trigger kind {kind!r}")
        tid = new_id("trg")
        with self.tx() as c:
            c.execute(
                "INSERT INTO triggers(id, name, kind, schedule, spec_json, budget_usd, secret, next_fire_at,"
                " created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    tid,
                    name,
                    kind,
                    schedule,
                    json.dumps(spec, sort_keys=True),
                    budget_usd,
                    secret,
                    next_fire_at,
                    _now(),
                ),
            )
        return tid

    @staticmethod
    def _trigger(row: sqlite3.Row) -> dict[str, Any]:
        d = dict(row)
        d["spec"] = json.loads(d.pop("spec_json"))
        d["enabled"] = bool(d["enabled"])
        return d

    def get_trigger(self, name: str) -> dict[str, Any] | None:
        row = self._conn.execute("SELECT * FROM triggers WHERE name=? OR id=?", (name, name)).fetchone()
        return None if row is None else self._trigger(row)

    def list_triggers(self) -> list[dict[str, Any]]:
        return [self._trigger(r) for r in self._conn.execute("SELECT * FROM triggers ORDER BY created_at")]

    def due_triggers(self, now: float) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM triggers WHERE kind='cron' AND enabled=1 AND next_fire_at<=? ORDER BY next_fire_at",
            (now,),
        ).fetchall()
        return [self._trigger(r) for r in rows]

    def set_trigger_enabled(self, name: str, enabled: bool) -> None:
        with self.tx() as c:
            if (
                c.execute(
                    "UPDATE triggers SET enabled=? WHERE name=? OR id=?", (int(enabled), name, name)
                ).rowcount
                == 0
            ):
                raise KeyError(name)

    def delete_trigger(self, name: str) -> None:
        with self.tx() as c:
            if c.execute("DELETE FROM triggers WHERE name=? OR id=?", (name, name)).rowcount == 0:
                raise KeyError(name)

    def advance_trigger(
        self, trigger_id: str, expected_next: float | None, next_fire_at: float | None
    ) -> bool:
        """Move a trigger past a fire. CAS on ``next_fire_at`` so two schedulers cannot both advance it."""
        with self.tx() as c:
            cur = c.execute(
                "UPDATE triggers SET next_fire_at=?, last_fired_at=?, fired=fired+1 WHERE id=? AND next_fire_at IS ?",
                (next_fire_at, _now(), trigger_id, expected_next),
            )
            return cur.rowcount == 1

    def find_run_by_dedupe(self, dedupe_key: str) -> str | None:
        row = self._conn.execute("SELECT id FROM runs WHERE dedupe_key=?", (dedupe_key,)).fetchone()
        return None if row is None else row["id"]

    # ------------------------------------------------------------------ notification outbox
    def enqueue_notification(self, park_id: str, channel: str) -> bool:
        key = f"{park_id}:{channel}"
        with self.tx() as c:
            cur = c.execute(
                "INSERT OR IGNORE INTO notifications(key, park_id, channel, status, next_try_at, created_at)"
                " VALUES (?,?,?,?,?,?)",
                (key, park_id, channel, "pending", _now(), _now()),
            )
            return cur.rowcount == 1

    def due_notifications(self, now: float) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM notifications WHERE status='pending' AND next_try_at<=? ORDER BY created_at",
            (now,),
        ).fetchall()
        return [dict(r) for r in rows]

    def notifications(self, park_id: str | None = None) -> list[dict[str, Any]]:
        if park_id is None:
            rows = self._conn.execute("SELECT * FROM notifications ORDER BY created_at").fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM notifications WHERE park_id=? ORDER BY created_at", (park_id,)
            ).fetchall()
        return [dict(r) for r in rows]

    def mark_notification(
        self,
        key: str,
        ok: bool,
        error: str | None = None,
        retry_at: float | None = None,
        give_up: bool = False,
    ) -> None:
        with self.tx() as c:
            if ok:
                c.execute(
                    "UPDATE notifications SET status='sent', attempts=attempts+1, sent_at=?, last_error=NULL"
                    " WHERE key=?",
                    (_now(), key),
                )
            else:
                c.execute(
                    "UPDATE notifications SET status=?, attempts=attempts+1, last_error=?, next_try_at=? WHERE key=?",
                    ("failed" if give_up else "pending", (error or "")[:500], retry_at or _now(), key),
                )

    # ------------------------------------------------------------------ sessions
    def create_session(self, title: str, template: dict[str, Any], budget_usd: float) -> str:
        sid = new_id("ses")
        with self.tx() as c:
            c.execute(
                "INSERT INTO sessions(id, title, template_json, budget_usd, created_at) VALUES (?,?,?,?,?)",
                (sid, title, json.dumps(template, sort_keys=True), budget_usd, _now()),
            )
        return sid

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        row = self._conn.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
        if row is None:
            return None
        d = dict(row)
        d["template"] = json.loads(d.pop("template_json"))
        return d

    def list_sessions(self) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT id, title, budget_usd, created_at FROM sessions ORDER BY created_at"
        )
        return [dict(r) for r in rows]

    def add_session_message(self, session_id: str, text: str) -> int:
        with self.tx() as c:
            if c.execute("SELECT 1 FROM sessions WHERE id=?", (session_id,)).fetchone() is None:
                raise KeyError(session_id)
            seq = c.execute(
                "SELECT COALESCE(MAX(seq), 0) + 1 AS n FROM session_messages WHERE session_id=?",
                (session_id,),
            ).fetchone()["n"]
            c.execute(
                "INSERT INTO session_messages(session_id, seq, text, created_at) VALUES (?,?,?,?)",
                (session_id, seq, text, _now()),
            )
            return int(seq)

    def session_messages(self, session_id: str) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM session_messages WHERE session_id=? ORDER BY seq", (session_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    def pending_session_messages(self) -> list[dict[str, Any]]:
        """The oldest message without a run, per session (later ones wait behind it)."""
        rows = self._conn.execute(
            "SELECT m.* FROM session_messages m WHERE m.run_id IS NULL AND m.seq = ("
            " SELECT MIN(seq) FROM session_messages WHERE session_id=m.session_id AND run_id IS NULL)"
            " ORDER BY m.created_at"
        ).fetchall()
        return [dict(r) for r in rows]

    def bind_session_message(self, session_id: str, seq: int, run_id: str) -> None:
        with self.tx() as c:
            c.execute(
                "UPDATE session_messages SET run_id=? WHERE session_id=? AND seq=? AND run_id IS NULL",
                (run_id, session_id, seq),
            )
