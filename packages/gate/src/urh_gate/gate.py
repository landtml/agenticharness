"""The step gate: decides pass, fail or park for one step's artifact.

The gate reads the artifact from the workspace and ignores the worker's
self-report. Phases run cheapest first and stop at the first failure:

  load        the target file exists, is small enough, is UTF-8, parses
  static      policy scan of the source (static.py)
  examples    hidden examples and regression inputs grown from past escapes
  edges       boundary inputs listed by the contract's generators
  random      seeded random inputs, differential against the reference
  targeted    inputs aimed at the literals in the candidate's own source
              (thresholds, magic values) and a ladder of common limits
  properties  relational checks across calls (round trips, invariants)
  determinism a sample replayed in a fresh process, reversed order and a
              different hash seed, must give identical outputs; the same sample
              replayed at the end of one long process (every case run in
              between) must not drift

Every call also fails on input mutation, a wrong exception type, an output
that is not a plain builtin value, a timeout, or a sandbox violation.

The random seed is derived from the gate salt, the contract name and the
artifact's hash, so a verdict replays exactly for the same artifact, while
any edit to the artifact gets fresh inputs. That stops a repair loop from
memorising counterexamples.
"""

import hashlib
import json
import os
from dataclasses import dataclass, field

from . import sandbox, static, targeted, values
from .contract import Ref

GATE_VERSION = "2.0.0"
PASS, FAIL, PARK = "pass", "fail", "park"
CHUNK = 400


@dataclass
class Outcome:
    kind: str  # value | error | wrong_error | bad | timeout | missing | skipped | violation
    value: object = None
    detail: str = ""
    mutated: bool = False

    def show(self):
        if self.kind == "value":
            return values.short_repr(self.value)
        if self.kind == "error":
            return "raises ValueError"
        return "{}{}".format(self.kind, (": " + self.detail) if self.detail else "")


@dataclass
class Verdict:
    status: str
    contract: str
    artifact_sha256: str = ""
    seed: int = 0
    reasons: list = field(default_factory=list)
    phases: dict = field(default_factory=dict)
    counterexample: dict = None
    findings: list = field(default_factory=list)
    claimed_by_worker: object = None  # recorded for audit, never consulted
    gate_version: str = GATE_VERSION

    @property
    def passed(self):
        return self.status == PASS

    def to_json(self):
        return {
            "status": self.status,
            "contract": self.contract,
            "artifact_sha256": self.artifact_sha256,
            "seed": self.seed,
            "reasons": self.reasons,
            "phases": self.phases,
            "counterexample": self.counterexample,
            "findings": [f.to_json() for f in self.findings],
            "claimed_by_worker": self.claimed_by_worker,
            "gate_version": self.gate_version,
        }

    def repair_note(self, limit=600):
        """Short, path-free note for the worker's next attempt.

        Contains only check names, the minimal failing input and what was
        expected. Marked as untrusted data by the caller's prompt builder.
        """
        if self.status == PASS:
            return ""
        lines = [f"Gate verdict: {self.status}."]
        for r in self.reasons[:3]:
            lines.append("- " + r)
        ce = self.counterexample
        if ce:
            lines.append("Smallest failing call: {}({})".format(ce["fn"], ", ".join(ce["args"])))
            lines.append("Expected: {}".format(ce["expected"]))
            lines.append("Got: {}".format(ce["got"]))
        lines.append("The checks are not reachable from the workspace; fix the code, not the tests.")
        note = "\n".join(lines)
        return note if len(note) <= limit else note[: limit - 3] + "..."


class Gate:
    PHASES = ("static", "examples", "edges", "random", "targeted", "properties", "determinism")

    def __init__(self, contract, *, salt=None, random_scale=1.0, disable=()):
        """``disable`` turns phases off; used only for ablations and baselines."""
        self.c = contract
        self.salt = salt if salt is not None else secret_salt() + "|" + contract.gate_salt
        self.random_scale = random_scale
        unknown = set(disable) - set(self.PHASES)
        if unknown:
            raise ValueError(f"unknown phases: {sorted(unknown)}")
        self.disable = frozenset(disable)

    # ------------------------------------------------------------------ API
    def evaluate(self, workspace, claimed=None):
        """Judge the artifact in ``workspace`` (a directory)."""
        path = os.path.join(workspace, self.c.target)
        try:
            with open(path, "rb") as fh:
                raw = fh.read(self.c.max_source_bytes + 1)
        except FileNotFoundError:
            return self._verdict(
                FAIL, "", 0, [f"target file {self.c.target} is missing"], {}, claimed=claimed
            )
        except OSError as e:
            return self._verdict(
                FAIL, "", 0, [f"target file unreadable: {type(e).__name__}"], {}, claimed=claimed
            )
        return self.evaluate_source(raw, claimed=claimed)

    def evaluate_source(self, raw, claimed=None):
        if isinstance(raw, str):
            raw = raw.encode("utf-8")
        sha = hashlib.sha256(raw).hexdigest()
        seed = int.from_bytes(
            hashlib.sha256((f"{self.salt}|{self.c.name}|{sha}").encode()).digest()[:8], "big"
        )
        phases = {}

        problems = self.c.strength_problems()
        if problems:
            return self._verdict(
                PARK, sha, seed, ["contract is vacuous: " + p for p in problems], phases, claimed=claimed
            )

        if len(raw) > self.c.max_source_bytes:
            return self._verdict(FAIL, sha, seed, ["target file too large"], phases, claimed=claimed)
        try:
            source = raw.decode("utf-8")
        except UnicodeDecodeError:
            return self._verdict(FAIL, sha, seed, ["target file is not UTF-8"], phases, claimed=claimed)
        phases["load"] = "ok"

        findings = static.scan(source, self.c.allowed_imports)
        if "static" in self.disable:
            findings = [f for f in findings if f.rule == "syntax"]
        blocks = [f for f in findings if f.level == "block"]
        phases["static"] = {"blocking": len(blocks), "warnings": len(findings) - len(blocks)}
        if blocks:
            reasons = ["static policy: %s (line %d)" % (f.detail, f.line) for f in blocks[:5]]
            return self._verdict(FAIL, sha, seed, reasons, phases, findings=findings, claimed=claimed)

        rng_seed = seed
        cases = []  # (phase, kind, payload) where kind is "fn" or "prop"

        def on(phase):
            return phase not in self.disable

        if on("examples"):
            cases += [("examples", "ex", e) for e in self.c.examples]
            cases += [("examples", "fn", (fn, list(args))) for fn, args in self.c.regressions]
        if on("edges"):
            for f in self.c.functions:
                for args in f.args.edges():
                    cases.append(("edges", "fn", (f.name, list(args))))
        import random

        rng = random.Random(rng_seed)
        # A second stream that does not depend on the artifact: a candidate cannot
        # grind its own bytes to steer every random input away from a bad region.
        fixed = random.Random(
            int.from_bytes(hashlib.sha256((f"{self.salt}|{self.c.name}|fixed").encode()).digest()[:8], "big")
        )
        if on("random"):
            for f in self.c.functions:
                n = max(1, int(f.random_cases * self.random_scale))
                for i in range(n):
                    src_rng = fixed if i % 2 else rng
                    cases.append(("random", "fn", (f.name, f.args.draw(src_rng, i * 100 // n))))
        if on("targeted"):
            trng = targeted.seeded(rng_seed)
            for f in self.c.functions:
                bases = targeted.bases_for(self.c, f.name, trng)
                budget = max(1, int(self.c.targeted_cases * self.random_scale))
                for args in targeted.variants(bases, source, trng, budget=budget, domain=f.domain):
                    cases.append(("targeted", "fn", (f.name, args)))
        if on("properties"):
            for p in self.c.properties:
                n = max(1, int(p.cases * self.random_scale))
                for x in p.inputs.edges()[:20]:
                    cases.append(("properties", "prop", (p, x)))
                for i in range(n):
                    cases.append(("properties", "prop", (p, p.inputs.draw(rng, i * 100 // n))))

        for phase in ("examples", "edges", "random", "targeted", "properties"):
            batch = [c for c in cases if c[0] == phase]
            result = self._run_cases(source, batch, hash_seed=seed % 4294967295)
            if result["park"]:
                return self._verdict(
                    PARK, sha, seed, result["park"], phases, findings=findings, claimed=claimed
                )
            phases[phase] = {"run": result["run"], "failed": 1 if result["failure"] else 0}
            if result["failure"]:
                reason, ce = result["failure"]
                if ce and ce.get("_shrinkable"):
                    ce = self._shrink(source, ce, seed)
                if ce:
                    ce.pop("_shrinkable", None)
                    ce.pop("_raw", None)
                return self._verdict(
                    FAIL, sha, seed, [reason], phases, counterexample=ce, findings=findings, claimed=claimed
                )

        if not on("determinism"):
            return self._verdict(PASS, sha, seed, [], phases, findings=findings, claimed=claimed)
        # Determinism and endurance. Process A runs a sample, then every case of
        # the earlier phases, then the sample again: a result that drifts within
        # one long-lived process means hidden state across calls (a call-count
        # sleeper). Process B runs the sample reversed with another hash seed.
        sample = [c for c in cases if c[1] == "fn"][:120] + [c for c in cases if c[1] == "prop"][:30]
        k = len(sample)
        long_run = self._raw_outputs(source, sample + cases + sample, hash_seed=(seed // 7) % 4294967295)
        second = self._raw_outputs(source, list(reversed(sample)), hash_seed=(seed // 13 + 1) % 4294967295)
        if long_run is None or second is None:
            return self._verdict(
                FAIL,
                sha,
                seed,
                ["candidate crashed during determinism replay"],
                phases,
                findings=findings,
                claimed=claimed,
            )
        head, tail = long_run[:k], long_run[-k:]
        second = list(reversed(second))  # per-case groups, back in original order
        drift = next((i for i, (a, b) in enumerate(zip(head, tail, strict=False)) if a != b), None)
        mismatch = next((i for i, (a, b) in enumerate(zip(head, second, strict=False)) if a != b), None)
        phases["determinism"] = {
            "run": len(long_run) + len(second),
            "failed": 0 if drift is None and mismatch is None else 1,
        }
        if drift is not None:
            return self._verdict(
                FAIL,
                sha,
                seed,
                ["stateful: results changed after %d calls in one process" % (len(long_run) - k)],
                phases,
                findings=findings,
                claimed=claimed,
            )
        if mismatch is not None:
            return self._verdict(
                FAIL,
                sha,
                seed,
                ["nondeterministic: same input gave different results across runs"],
                phases,
                findings=findings,
                claimed=claimed,
            )
        return self._verdict(PASS, sha, seed, [], phases, findings=findings, claimed=claimed)

    # ------------------------------------------------------------ internals
    def _verdict(self, status, sha, seed, reasons, phases, counterexample=None, findings=(), claimed=None):
        return Verdict(
            status=status,
            contract=self.c.name,
            artifact_sha256=sha,
            seed=seed,
            reasons=list(reasons),
            phases=phases,
            counterexample=counterexample,
            findings=list(findings),
            claimed_by_worker=claimed,
        )

    def _expand(self, case):
        """Turn a case into (program calls, checker)."""
        phase, kind, payload = case
        if kind == "fn" and phase == "targeted":
            fn, args = payload
            return [(fn, list(args))], ("fn", fn, args, "lenient")
        if kind == "ex":
            e = payload
            return [(e.fn, list(e.args))], ("ex", e)
        if kind == "fn":
            fn, args = payload
            return [(fn, list(args))], ("fn", fn, args)
        p, x = payload
        return list(p.calls(x)), ("prop", p, x)

    def _program(self, calls, offset):
        prog = []
        for fn, args in calls:
            enc = []
            for a in args:
                if isinstance(a, Ref):
                    enc.append(sandbox.ref(offset + a.index))
                else:
                    enc.append(values.encode(a))
            prog.append({"fn": fn, "args": enc})
        return prog

    def _execute(self, source, cases, hash_seed):
        """Run cases in chunks; returns list of (case, calls, outcomes) or a problem string."""
        out = []
        i = 0
        while i < len(cases):
            chunk, prog, spans = [], [], []
            while i < len(cases) and len(prog) < CHUNK:
                calls, checker = self._expand(cases[i])
                spans.append((len(prog), len(calls)))
                prog += self._program(calls, len(prog))
                chunk.append((cases[i], calls, checker))
                i += 1
            report = sandbox.run_program(
                source, prog, per_call_timeout=self.c.per_call_timeout, hash_seed=hash_seed
            )
            if not report.ok:
                return report.problem
            if report.import_status != "ok":
                return "import:" + report.import_status, report.violations
            outcomes = [self._outcome(r, report.violations) for r in report.calls]
            for (case, calls, checker), (start, n) in zip(chunk, spans, strict=False):
                out.append((case, calls, checker, outcomes[start : start + n], report.violations))
        return out

    def _outcome(self, r, violations):
        mutated = bool(r.get("mutated"))
        if r.get("builtins"):
            return Outcome("violation", detail="modified builtins", mutated=mutated)
        if "ok" in r:
            return Outcome("value", values.decode(r["ok"]), mutated=mutated)
        if "raise" in r:
            if r["raise"] == "RuntimeError" and violations:
                return Outcome("violation", detail=violations[0], mutated=mutated)
            if r.get("value_error"):
                return Outcome("error", mutated=mutated)
            return Outcome("wrong_error", detail=r["raise"], mutated=mutated)
        if "bad" in r:
            return Outcome("bad", detail=r["bad"], mutated=mutated)
        if r.get("timeout"):
            return Outcome("timeout")
        if "missing" in r:
            return Outcome("missing", detail="function {} not defined".format(r["missing"]))
        return Outcome("skipped")

    def _expected(self, fn, args):
        """Reference outcome, or raise ContractBug."""
        spec = self.c.function(fn)
        if spec.reference is None:
            return None
        try:
            return Outcome("value", spec.reference(*_copy(args)))
        except spec.error:
            return Outcome("error")
        except Exception as e:  # the oracle itself is broken for this input
            raise ContractBug(f"reference {fn} raised {type(e).__name__} on {values.short_repr(args)}") from e

    def _matches(self, fn, expected, got):
        if got.mutated:
            return False, "modified its input"
        if got.kind == "violation":
            return False, f"sandbox violation ({got.detail})"
        if got.kind in ("timeout", "missing", "bad", "wrong_error", "skipped"):
            return False, got.show()
        if expected is None:
            return True, ""
        if expected.kind == "error":
            return (got.kind == "error"), "should raise ValueError"
        if got.kind != "value":
            return False, "raised ValueError on a valid input"
        cmp = self.c.function(fn).compare
        try:
            same = (
                cmp(expected.value, got.value)
                if cmp
                else values.canon(expected.value) == values.canon(got.value)
            )
        except Exception:
            same = False
        return same, "wrong result"

    def _check(self, checker, outcomes, violations):
        """Return None if the case passed, else (reason, counterexample)."""
        if violations:
            return (f"sandbox violation: {violations[0]}", None)
        kind = checker[0]
        if kind == "ex":
            e = checker[1]
            exp = Outcome("error") if e.raises else Outcome("value", e.expect)
            ok, why = self._matches(e.fn, exp, outcomes[0])
            if ok:
                return None
            return (f"hidden example failed: {why}", _ce(e.fn, e.args, exp, outcomes[0]))
        if kind == "fn":
            fn, args = checker[1], checker[2]
            try:
                exp = self._expected(fn, args)
            except ContractBug:
                if len(checker) > 3:  # synthesized input outside the reference's domain: skip it
                    return None
                raise
            ok, why = self._matches(fn, exp, outcomes[0])
            if ok:
                return None
            ce = _ce(fn, args, exp, outcomes[0])
            ce["_shrinkable"] = True
            ce["_raw"] = (fn, args)
            return (f"{fn}: {why}", ce)
        _, prop, x = checker
        for o in outcomes:
            if o.mutated:
                return (f"property {prop.name}: a call modified its input", None)
            if o.kind in ("violation", "timeout", "missing", "bad", "wrong_error"):
                return (f"property {prop.name}: {o.show()}", None)
        try:
            res = prop.check(x, outcomes)
        except Exception as e:
            res = f"check raised {type(e).__name__}"
        if res is True:
            return None
        return (
            "property {} failed{}".format(prop.name, (": " + res) if isinstance(res, str) else ""),
            {
                "fn": prop.name,
                "args": [values.short_repr(x)],
                "expected": "property holds",
                "got": " / ".join(o.show() for o in outcomes)[:200],
            },
        )

    def _run_cases(self, source, cases, hash_seed):
        res = {"run": 0, "failure": None, "park": None}
        if not cases:
            return res
        try:
            executed = self._execute(source, cases, hash_seed)
        except ContractBug as e:
            res["park"] = [str(e)]
            return res
        if isinstance(executed, str):
            res["failure"] = (f"candidate process failed: {executed}", None)
            return res
        if isinstance(executed, tuple):
            status, violations = executed
            why = status
            if violations:
                why += f" (sandbox: {violations[0]})"
            res["failure"] = (f"candidate failed at import: {why}", None)
            return res
        try:
            for _case, _calls, checker, outcomes, violations in executed:
                res["run"] += 1
                bad = self._check(checker, outcomes, violations)
                if bad:
                    res["failure"] = bad
                    return res
        except ContractBug as e:
            res["park"] = [str(e)]
        return res

    def _raw_outputs(self, source, cases, hash_seed):
        """Raw runner entries grouped per case, for byte-level comparison."""
        prog, spans = [], []
        for c in cases:
            calls, _ = self._expand(c)
            spans.append((len(prog), len(calls)))
            prog += self._program(calls, len(prog))
        report = sandbox.run_program(
            source, prog, per_call_timeout=self.c.per_call_timeout, hash_seed=hash_seed
        )
        if not report.ok or report.import_status != "ok" or len(report.calls) != len(prog):
            return None
        return [json.dumps(report.calls[a : a + n], sort_keys=True) for a, n in spans]

    def _shrink(self, source, ce, seed, rounds=30):
        fn, args = ce["_raw"]
        spec = self.c.function(fn)
        best = (args, ce)
        for _ in range(rounds):
            try:
                candidates = [a for a in spec.args.shrink(best[0]) if a != best[0]][:40]
            except Exception:
                break
            if not candidates:
                break
            batch = [("random", "fn", (fn, a)) for a in candidates]
            try:
                executed = self._execute(source, batch, hash_seed=seed % 4294967295)
            except ContractBug:
                break
            if not isinstance(executed, list):
                break
            improved = False
            for _case, _calls, checker, outcomes, violations in executed:
                try:
                    bad = self._check(checker, outcomes, violations)
                except ContractBug:
                    continue
                if bad and bad[1]:
                    best = (checker[2], bad[1])
                    improved = True
                    break
            if not improved:
                break
        return best[1]


class ContractBug(Exception):
    pass


def secret_salt():
    """The gate's private salt: URH_GATE_SALT, else a secret file created on first use.

    Workers must not be able to read it (keep the file outside their sandbox);
    with it unknown, a candidate cannot predict its random inputs. The seed of
    every verdict is recorded, so a verdict can still be replayed.
    """
    env = os.environ.get("URH_GATE_SALT")
    if env:
        return env
    path = os.environ.get("URH_GATE_SALT_FILE") or os.path.join(
        os.path.expanduser("~"), ".config", "urh", "gate-salt"
    )
    try:
        with open(path) as fh:
            value = fh.read().strip()
        if value:
            return value
    except OSError:
        pass
    import secrets

    value = secrets.token_hex(32)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as fh:
            fh.write(value)
    except FileExistsError:
        with open(path) as fh:
            return fh.read().strip() or value
    except OSError:
        pass  # read-only home: the salt lives for this process only
    return value


def _copy(args):
    import copy

    return copy.deepcopy(list(args))


def _ce(fn, args, expected, got):
    return {
        "fn": fn,
        "args": [values.short_repr(a, 80) for a in args],
        "expected": expected.show() if expected else "(no oracle)",
        "got": got.show(),
    }
