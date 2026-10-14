"""Run orchestrator: the control loop is code.

It holds the run's lease (renewed by a heartbeat, fenced by epoch), the pinned
versions and one global budget, and routes each gate verdict: pass commits and
moves on, fail starts a bounded repair that must differ, unsure parks. The loop
keeps no state of its own; any process can take an expired lease and continue
from the journal and the last verified commit (durability level D1).
"""

from __future__ import annotations

import os
import socket
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from . import HARNESS_VERSION
from .blobs import BlobStore
from .checkpoint import GitCheckpoint
from .context import step_message, system_blocks
from .effects import EffectAdapter, EffectGuard, OutboxFileAdapter
from .gate import ScriptGate, Verdict, default_vetter
from .gateway import DEFAULT_MODELS, ModelGateway, Provider, ProviderDown
from .journal import SCHEMA_VERSION, BudgetExceeded, Journal, LeaseLost
from .judge import LLMJudge
from .manager import CodeManager, LLMManager, Manager
from .planner import PlanningManager
from .pricing import PriceBook
from .spec import StepSpec, TaskSpec
from .worker import Worker, Workspace

SPEC_EFFECT_BASE = 1000  # effect indexes for effects declared in the spec, after the worker's own


class AdmissionDenied(Exception):
    pass


@dataclass
class HarnessConfig:
    lease_ttl: float = 30.0
    heartbeat_s: float = 10.0
    max_active_runs: int = 8
    global_spend_cap_usd: float | None = None
    worker_effort: str = "medium"
    manager_effort: str = "medium"
    manager: str = "planner"  # planner: plan milestones, expand, replan | stepwise: one manager call per step
    planner_effort: str = "high"
    provider_retries: int = 3
    provider_backoff_s: float = 2.0
    command_timeout: float = 60.0
    # Which model plays which role. Any provider's model ids work; these are only the defaults.
    models: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_MODELS))
    # Policies that resolve would-be parks without a person. A park is a failure mode, not a normal path.
    auto_topup_usd: float = 0.0  # budget added automatically when a run runs dry ...
    max_auto_topups: int = 0  # ... at most this many times per run
    vet_plan_checks: bool = True  # screen planner-written checks before they may pass a step
    outage_wake_s: float = 300.0  # an outage park wakes itself after this long
    use_judge: bool = True  # a model judge decides steps no script check covers
    escalate: bool = True  # one attempt on the escalation model before repairs_exhausted parks


class _Heartbeat(threading.Thread):
    def __init__(self, journal: Journal, run_id: str, epoch: int, ttl: float, every: float):
        super().__init__(daemon=True)
        self.journal, self.run_id, self.epoch, self.ttl, self.every = journal, run_id, epoch, ttl, every
        self.stop_event = threading.Event()
        self.lost = threading.Event()

    def run(self) -> None:
        while not self.stop_event.wait(self.every):
            try:
                self.journal.renew_lease(self.run_id, self.epoch, self.ttl)
            except LeaseLost:
                self.lost.set()
                return
            except Exception:  # a busy database must not kill the heartbeat
                continue


class Harness:
    def __init__(
        self,
        home: str,
        provider: Provider,
        adapters: list[EffectAdapter] | None = None,
        config: HarnessConfig | None = None,
        owner: str | None = None,
        prices: PriceBook | None = None,
    ):
        self.home = os.path.abspath(home)
        os.makedirs(self.home, exist_ok=True)
        self.config = config or HarnessConfig()
        self.owner = owner or f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:6]}"
        self.journal = Journal(os.path.join(self.home, "journal.sqlite"))
        self.blobs = BlobStore(os.path.join(self.home, "blobs"))
        self.gateway = ModelGateway(
            self.journal,
            self.blobs,
            provider,
            retries=self.config.provider_retries,
            backoff_s=self.config.provider_backoff_s,
            prices=prices,
        )
        if adapters is None:
            adapters = [OutboxFileAdapter(os.path.join(self.home, "outbox"))]
        self.guard = EffectGuard(self.journal, adapters)
        self.worker = Worker(self.gateway, effort=self.config.worker_effort)
        self.llm_manager = LLMManager(self.gateway, effort=self.config.manager_effort)
        self.planner = PlanningManager(self.gateway, effort=self.config.planner_effort)
        self.judge = LLMJudge(self.gateway)
        self.vetter = default_vetter() if self.config.vet_plan_checks else None

    # ------------------------------------------------------------------ admission
    def submit(self, spec: TaskSpec, dedupe_key: str | None = None, budget_usd: float | None = None) -> str:
        """Turn a trigger into a run. A redelivered trigger maps to the run it already started."""
        budget = budget_usd if budget_usd is not None else spec.budget_usd
        cap = self.config.global_spend_cap_usd
        if dedupe_key is None and cap is not None and self.journal.total_spent() + budget > cap:
            raise AdmissionDenied(f"global spend cap ${cap:.2f} would be exceeded")
        pins = {
            "harness_version": HARNESS_VERSION,
            "schema_version": SCHEMA_VERSION,
            **self.gateway.pins_for(self.config.models),
        }
        run_id, created = self.journal.create_run(spec.to_dict(), pins, budget, dedupe_key=dedupe_key)
        if created and cap is not None and self.journal.total_spent() > cap + budget:
            raise AdmissionDenied(f"global spend cap ${cap:.2f} exceeded")
        return run_id

    def runnable(self) -> list[str]:
        """Queued runs, and running runs whose lease expired (their process died)."""
        now = time.time()
        out = [r.id for r in self.journal.list_runs("queued")]
        out += [r.id for r in self.journal.list_runs("running") if r.lease_expires < now]
        return out

    def wake_due(self) -> list[str]:
        """Answer parks that resolve themselves with time (provider outages). Returns requeued run ids."""
        woke = []
        now = time.time()
        for park in self.journal.parks(status="open"):
            wake_at = park["preconditions"].get("wake_at")
            if wake_at is not None and wake_at <= now and not self.gateway.breaker.is_open():
                try:
                    woke.append(self.journal.answer_park(park["id"], "auto: retry after cooldown"))
                except ValueError:
                    continue  # someone else answered it first
        return woke

    def run_pending(self) -> dict[str, str]:
        self.wake_due()
        results = {}
        for run_id in self.runnable():
            if self.journal.count_active() >= self.config.max_active_runs:
                break  # backpressure: leave the rest queued
            results[run_id] = self.run(run_id)
        return results

    # ------------------------------------------------------------------ the loop
    def run(self, run_id: str) -> str:
        """Drive one run until it is done, failed, parked, or we lose its lease. Returns the status."""
        cfg = self.config
        epoch = self.journal.acquire_lease(run_id, self.owner, cfg.lease_ttl)
        if epoch is None:
            return self.journal.get_run(run_id).status
        hb = _Heartbeat(self.journal, run_id, epoch, cfg.lease_ttl, cfg.heartbeat_s)
        hb.start()
        ckpt = GitCheckpoint(os.path.join(self.home, "runs", run_id))
        try:
            return self._drive(run_id, epoch, ckpt)
        except LeaseLost:
            return "lease_lost"
        finally:
            hb.stop_event.set()
            hb.join(timeout=5)
            self.journal.release_lease(run_id, epoch)
            ckpt.cleanup_epoch(epoch)

    def _park(
        self,
        run_id: str,
        epoch: int,
        step_index: int,
        reason: str,
        question: str,
        verified: str | None,
        extra: dict[str, Any] | None = None,
    ) -> str:
        pre = {"verified_commit": verified, **(extra or {})}
        if reason == "outage":
            pre["wake_at"] = time.time() + self.config.outage_wake_s
        self.journal.park(run_id, epoch, step_index, reason, question, pre)
        return "parked"

    def _replan(
        self,
        manager: Manager,
        run_id: str,
        epoch: int,
        pins: dict[str, Any],
        spec: TaskSpec,
        i: int,
        failed: list[dict[str, Any]],
        ckpt: GitCheckpoint,
        verified: str,
    ) -> bool:
        """Ask a planning manager for a different step N instead of parking. False when it can't or won't."""
        replan = getattr(manager, "replan", None)
        if replan is None:
            return False
        failures = [f for a in failed[-2:] for f in ((a.get("verdict") or {}).get("failures") or [])]
        try:
            step = replan(
                run_id=run_id,
                epoch=epoch,
                pins=pins,
                spec=spec,
                step_index=i,
                failures=failures,
                files=_ls_tree(ckpt, verified),
            )
        except (BudgetExceeded, ProviderDown, ValueError) as e:
            self.journal.event(run_id, epoch, "replan_failed", step_index=i, error=repr(e)[:300])
            return False
        if step is None:
            return False
        self.journal.replan_step(run_id, epoch, i, step, manager.source)
        return True

    def _manager_for(self, spec: TaskSpec) -> Manager:
        if spec.steps is not None:
            return CodeManager()
        return self.planner if self.config.manager == "planner" else self.llm_manager

    def _drive(self, run_id: str, epoch: int, ckpt: GitCheckpoint) -> str:
        run = self.journal.get_run(run_id)
        spec = TaskSpec.from_dict(run.spec)
        pins = run.pins
        if pins.get("schema_version", SCHEMA_VERSION) > SCHEMA_VERSION:
            return self._park(
                run_id,
                epoch,
                run.step_index,
                "version",
                f"run was started on journal schema {pins['schema_version']}; this harness is older",
                run.verified_commit,
            )
        self.journal.release_stale_reservations(run_id, epoch)
        root = ckpt.init(spec.seed_dir)
        if run.verified_commit is None:
            self.journal.set_verified_commit(run_id, epoch, root)
        verified = self.journal.get_run(run_id).verified_commit
        assert verified is not None
        head = ckpt.verified_head()
        if head != verified:
            # The ref moved past the journal (crash between promote and complete_step). Only a commit
            # the gate passed for the current step may stay ahead; anything else is rolled back.
            current = self.journal.get_run(run_id).step_index
            passed = {
                a["commit_sha"] for a in self.journal.attempts(run_id, current) if a["status"] == "pass"
            }
            if head not in passed:
                ckpt.force_ref(verified)
                self.journal.event(run_id, epoch, "ref_rolled_back", head=head, verified=verified)

        # Parked answers are claimed once, and only used if their premise still holds.
        answers: list[str] = []
        approved: set[str] = set()
        for park in self.journal.claim_answers(run_id, epoch, self.owner):
            if park["preconditions"].get("verified_commit") not in (None, verified):
                self.journal.event(run_id, epoch, "answer_stale", park_id=park["id"])
                continue
            text = (park["answer"] or "").strip()
            if park["reason"] == "effect" and text.lower().startswith("approve"):
                approved.update(park["preconditions"].get("effect_keys", []))
            elif park["reason"] == "effect":
                for key in park["preconditions"].get("effect_keys", []):
                    self.journal.mark_effect(
                        run_id, epoch, key, "failed", {"reason": f"declined: {text[:200]}"}
                    )
            elif park["reason"] == "budget":
                pass  # top-ups arrive via add_budget; the answer only wakes the run
            elif not text.startswith("auto:"):
                answers.append(text)

        # Effects of steps that verified before a crash still have to fire (outbox).
        for idx in range(run.step_index):
            pending = [e for e in self.journal.effects(run_id, idx) if e["status"] not in ("done", "failed")]
            if pending:
                flushed = self.guard.flush(run_id, epoch, idx, approved)
                if flushed.parked:
                    return self._park(
                        run_id,
                        epoch,
                        idx,
                        "effect",
                        "Approve these outward actions? " + "; ".join(r for _, r in flushed.parked),
                        verified,
                        {"effect_keys": [k for k, _ in flushed.parked]},
                    )

        manager = self._manager_for(spec)
        while True:
            run = self.journal.get_run(run_id)
            i = run.step_index
            if i >= spec.max_steps:
                self.journal.set_status(run_id, epoch, "failed", "step limit reached")
                return "failed"
            step_dict = self.journal.planned_step(run_id, i)
            if step_dict is None:
                history = [
                    {"step_index": k, "title": (self.journal.planned_step(run_id, k) or {}).get("title", "")}
                    for k in range(i)
                ]
                files = [p for p in _ls_tree(ckpt, verified)]
                try:
                    proposed = manager.next_step(
                        run_id=run_id,
                        epoch=epoch,
                        pins=pins,
                        spec=spec,
                        step_index=i,
                        history=history,
                        files=files,
                    )
                except BudgetExceeded:
                    if self._auto_topup(run_id, epoch):
                        continue
                    return self._park(
                        run_id,
                        epoch,
                        i,
                        "budget",
                        "The run's budget is spent. Add budget to continue.",
                        verified,
                    )
                except ProviderDown as e:
                    return self._park(
                        run_id, epoch, i, "outage", f"Model provider unavailable: {e}", verified
                    )
                except ValueError as e:  # the manager's answer could not be used (bad JSON, rejected plan)
                    return self._park(
                        run_id,
                        epoch,
                        i,
                        "plan",
                        f"The manager could not plan step {i + 1}: {e}"[:1500],
                        verified,
                    )
                step_dict = self.journal.plan_step(run_id, epoch, i, proposed, manager.source)
            if step_dict.get("done"):
                self.journal.set_status(run_id, epoch, "done", None)
                return "done"
            step = StepSpec.from_dict(step_dict)

            prior = self.journal.attempts(run_id, i)
            passed = [a for a in prior if a["status"] == "pass" and a.get("commit_sha")]
            if passed:
                # The gate already passed this step but we crashed before the journal advanced.
                # Finish committing it instead of redoing verified work.
                commit = passed[-1]["commit_sha"]
                self.journal.event(run_id, epoch, "recovered_pass", step_index=i, commit=commit)
                parked = self._commit_pass(run_id, epoch, ckpt, i, step, commit, verified, approved)
                verified = commit
                if parked:
                    return parked
                continue
            failed = [a for a in prior if a["status"] == "fail"]
            role = "worker"
            if len(failed) > spec.max_repairs and self._may_escalate(run_id, i, pins, len(failed), spec):
                role = "escalation"
                self.journal.event(
                    run_id, epoch, "escalated", step_index=i, model=pins["models"]["escalation"]
                )
            elif len(failed) > spec.max_repairs:
                if self._replan(manager, run_id, epoch, pins, spec, i, failed, ckpt, verified):
                    continue
                return self._park(
                    run_id,
                    epoch,
                    i,
                    "repairs_exhausted",
                    f"Step '{step.title}' failed its checks {len(failed)} times. "
                    f"Last failures: {'; '.join((failed[-1]['verdict'] or {}).get('failures', [])[:5])}",
                    verified,
                )
            attempt = self.journal.begin_attempt(run_id, epoch, i)
            repair = None
            start_from = verified
            if failed:
                last = failed[-1]
                repair = {"attempt": attempt, "failures": (last["verdict"] or {}).get("failures", [])}
                if last.get("commit_sha"):
                    start_from = last["commit_sha"]  # repair the failed work rather than redo it
            ws = Workspace(
                ckpt.prepare_workspace(epoch, start_from), command_timeout=self.config.command_timeout
            )
            done_titles = [(self.journal.planned_step(run_id, k) or {}).get("title", "") for k in range(i)]
            message = step_message(
                step, i, len(spec.steps) if spec.steps else None, done_titles, repair, answers
            )
            answers = []

            def propose(idx: int, kind: str, payload: dict[str, Any], _i: int = i) -> str:
                return self.guard.propose(run_id, epoch, _i, idx, kind, payload)

            try:
                outcome = self.worker.run_step(
                    run_id=run_id,
                    epoch=epoch,
                    step_index=i,
                    attempt=attempt,
                    pins=pins,
                    system=system_blocks(spec),
                    first_message=message,
                    workspace=ws,
                    propose=propose,
                    max_turns=spec.max_worker_turns,
                    effort=escalate_effort(step.effort or self.config.worker_effort, len(failed)),
                    role=role,
                )
            except BudgetExceeded:
                self.journal.record_verdict(
                    run_id, epoch, i, attempt, "aborted", None, None, {"summary": "budget"}
                )
                self.journal.discard_proposed_effects(run_id, epoch, i)
                if self._auto_topup(run_id, epoch):
                    continue
                return self._park(
                    run_id, epoch, i, "budget", "The run's budget is spent. Add budget to continue.", verified
                )
            except ProviderDown as e:
                self.journal.record_verdict(
                    run_id, epoch, i, attempt, "aborted", None, None, {"summary": "outage"}
                )
                self.journal.discard_proposed_effects(run_id, epoch, i)
                return self._park(run_id, epoch, i, "outage", f"Model provider unavailable: {e}", verified)
            self.journal.event(
                run_id,
                epoch,
                "worker_done",
                step_index=i,
                attempt=attempt,
                finished=outcome.finished,
                turns=outcome.turns,
                stop_reason=outcome.stop_reason,
            )

            tree, commit = ckpt.snapshot(epoch, verified, f"step {i + 1}: {step.title} (attempt {attempt})")
            if any(a["tree"] == tree for a in failed):
                # Identical to a failed attempt: it cannot pass, so skip the gate and count it as a failure.
                v = Verdict(
                    "fail",
                    "no progress: the attempt produced the same tree as a failed one",
                    failures=[*((failed[-1]["verdict"] or {}).get("failures", [])[:5]), "no progress"],
                )
                self.journal.record_verdict(run_id, epoch, i, attempt, "fail", tree, commit, v.to_dict())
                self.journal.discard_proposed_effects(run_id, epoch, i)
                continue

            verdict = ScriptGate(spec.gate, vetter=self.vetter).evaluate(ckpt, verified, commit, step)
            if verdict.status == "unsure" and self.config.use_judge:
                try:
                    verdict = self.judge.evaluate(
                        run_id=run_id,
                        epoch=epoch,
                        step_index=i,
                        attempt=attempt,
                        pins=pins,
                        ckpt=ckpt,
                        parent=verified,
                        candidate=commit,
                        step=step,
                    )
                except (BudgetExceeded, ProviderDown) as e:
                    verdict = Verdict("unsure", f"judge unavailable: {type(e).__name__}")
            self.journal.record_verdict(
                run_id, epoch, i, attempt, verdict.status, tree, commit, verdict.to_dict()
            )
            if verdict.status == "fail":
                self.journal.discard_proposed_effects(run_id, epoch, i)
                continue
            if verdict.status == "unsure":
                self.journal.discard_proposed_effects(run_id, epoch, i)
                # Nothing can decide the step as written: the planner rewrites it (better checks) first.
                unsure = [{"verdict": {"failures": [verdict.summary, *verdict.failures]}}]
                if self._replan(manager, run_id, epoch, pins, spec, i, unsure, ckpt, verified):
                    continue
                return self._park(
                    run_id,
                    epoch,
                    i,
                    "unsure",
                    f"No check can decide step '{step.title}'. Review commit {commit[:12]}.",
                    verified,
                    {"candidate": commit},
                )

            parked = self._commit_pass(run_id, epoch, ckpt, i, step, commit, verified, approved)
            verified = commit
            if parked:
                return parked

    def _auto_topup(self, run_id: str, epoch: int) -> bool:
        """Apply the pre-set budget policy instead of parking. Returns True if budget was added."""
        cfg = self.config
        if cfg.auto_topup_usd <= 0 or cfg.max_auto_topups <= 0:
            return False
        used = sum(1 for e in self.journal.events(run_id) if e["kind"] == "auto_topup")
        if used >= cfg.max_auto_topups:
            return False
        self.journal.add_budget(run_id, cfg.auto_topup_usd)
        self.journal.event(run_id, epoch, "auto_topup", amount=cfg.auto_topup_usd, n=used + 1)
        return True

    def _may_escalate(self, run_id: str, i: int, pins: dict[str, Any], failures: int, spec: TaskSpec) -> bool:
        if not self.config.escalate or "escalation" not in pins.get("models", {}):
            return False
        if failures != spec.max_repairs + 1:
            return False
        return not any(
            e["kind"] == "escalated" and e.get("step_index") == i for e in self.journal.events(run_id)
        )

    def _commit_pass(
        self,
        run_id: str,
        epoch: int,
        ckpt: GitCheckpoint,
        i: int,
        step: StepSpec,
        commit: str,
        verified: str,
        approved: set[str],
    ) -> str | None:
        """Record spec-declared effects, promote the checkpoint, advance the journal, then fire the outbox.

        Every part is idempotent, so a crash anywhere in here is finished by the next process.
        """
        for k, eff in enumerate(step.effects):
            payload = dict(eff.get("payload", {}))
            if step.irreversible or eff.get("irreversible"):
                payload["irreversible"] = True
            self.guard.propose(run_id, epoch, i, SPEC_EFFECT_BASE + k, eff["kind"], payload)
        ckpt.promote(commit, verified)
        self.journal.complete_step(run_id, epoch, i, commit)
        flushed = self.guard.flush(run_id, epoch, i, approved)
        if flushed.parked:
            return self._park(
                run_id,
                epoch,
                i,
                "effect",
                "Approve these outward actions? " + "; ".join(r for _, r in flushed.parked),
                commit,
                {"effect_keys": [k for k, _ in flushed.parked]},
            )
        return None


EFFORT_LADDER = ["low", "medium", "high"]


def escalate_effort(effort: str, repairs: int) -> str:
    """Each repair runs the worker one effort level higher, capped at high."""
    if effort not in EFFORT_LADDER:
        return effort
    return EFFORT_LADDER[min(EFFORT_LADDER.index(effort) + repairs, len(EFFORT_LADDER) - 1)]


def _ls_tree(ckpt: GitCheckpoint, commit: str) -> list[str]:
    out = ckpt._git("ls-tree", "-r", "--name-only", commit).decode()
    return [p for p in out.splitlines() if p]
