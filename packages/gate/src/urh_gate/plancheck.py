"""Vetting planner-written check commands before they may gate a step.

A planner (a model) writes a shell command per step, e.g.
``python3 -c "from m import f; assert f(2) == 4"``. Such a check can be too
weak to mean anything: it can pass whatever the worker did (vacuous), test
only that a file exists, or run tests the worker wrote itself
(self-attestation). Before the harness lets a plan check decide "done", this
module audits the check itself against the step's own artifact:

  policy     static rules on the command text: no trivially true commands,
             no existence-only checks, no worker-written test files, no
             network tools
  positive   the check passes on the candidate tree
  vacuity    the check fails on the parent tree (the state before the step)
  sabotage   the check fails when the step's files are deleted, emptied, or
             every function in them is stubbed out
  mutation   the check kills at least ``min_kill`` of single-site mutants of
             the step's Python files

A check that clears all of these is ``trusted``. One that fails policy,
vacuity or sabotage is ``rejected``; one that only misses the mutation bar is
``weak``. The caller decides what weak means; the default harness policy is
that a step gated only by weak or rejected checks is unsure and goes back to
the planner rather than passing.
"""

import ast
import os
import re
import shlex
import shutil
import signal
import subprocess
import tempfile
from dataclasses import asdict, dataclass, field

from .audit import mutants as _mutants

TRUSTED, WEAK, REJECTED = "trusted", "weak", "rejected"

TRIVIAL = re.compile(r"^\s*(true|:|exit\s+0|echo\b.*|printf\b.*)\s*$")
EXISTENCE_ONLY = re.compile(
    r"^\s*(test\s+-[efsdr]\s+\S+|\[\s+-[efsdr]\s+\S+\s+\]|ls\s+\S+|stat\s+\S+|cat\s+\S+(\s*>\s*/dev/null)?|wc\s+.*)\s*$"
)
NETWORK = re.compile(r"\b(curl|wget|nc|ncat|ssh|scp|rsync|ftp|telnet|pip\s+install|npm\s+install)\b")
TEST_FILE = re.compile(r"(^|/)(test_[^/\s]*\.py|[^/\s]*_test\.py|tests?/)")


@dataclass
class Vetting:
    status: str
    reasons: list = field(default_factory=list)
    positive: bool = False
    vacuous: bool = False
    sabotage: dict = field(default_factory=dict)  # variant -> "fail" (good) | "pass" (bad)
    mutants_total: int = 0
    mutants_killed: int = 0

    @property
    def mutation_score(self):
        return self.mutants_killed / self.mutants_total if self.mutants_total else None

    def to_json(self):
        d = asdict(self)
        d["mutation_score"] = self.mutation_score
        return d


def policy_problems(cmd, step_files, worker_written=()):
    """Static reasons the command cannot be trusted, judged on its text alone."""
    problems = []
    text = cmd if isinstance(cmd, str) else " ".join(shlex.quote(c) for c in cmd)
    if not text.strip():
        return ["empty command"]
    if TRIVIAL.match(text):
        problems.append("trivially true command")
    if EXISTENCE_ONLY.match(text):
        problems.append("checks only that a file exists or can be read")
    if NETWORK.search(text):
        problems.append("uses the network or installs packages")
    if re.search(r"\|\|\s*(true|:|exit\s+0)\s*$", text) or re.search(r";\s*(true|exit\s+0)\s*$", text):
        problems.append("ends by forcing success")
    written = set(worker_written) | set(step_files)
    for token in re.split(r"[\s\"'=;|&()]+", text):
        token = token.strip()
        if token and token in written and TEST_FILE.search(token):
            problems.append(f"runs a test file the worker wrote: {token}")
    return problems


def _run(cmd, cwd, timeout):
    argv = ["/bin/bash", "-c", cmd] if isinstance(cmd, str) else list(cmd)
    env = {
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "HOME": cwd,
        "LANG": "C.UTF-8",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONHASHSEED": "0",
    }
    try:
        proc = subprocess.Popen(
            argv,
            cwd=cwd,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError:
        return False
    try:
        return proc.wait(timeout=timeout) == 0
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except OSError:
            pass
        proc.wait()
        return False


def _copy(tree, into):
    dst = os.path.join(into, "tree")
    if tree and os.path.isdir(tree):
        shutil.copytree(tree, dst, symlinks=True)
    else:
        os.makedirs(dst)
    return dst


def _stub_source(src, body):
    """Replace every function body with ``body`` (a statement string)."""
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return ""
    stmt = ast.parse(body).body

    class Stub(ast.NodeTransformer):
        def visit_FunctionDef(self, node):
            node.body = [s for s in stmt]
            return node

        visit_AsyncFunctionDef = visit_FunctionDef

    return ast.unparse(ast.fix_missing_locations(Stub().visit(tree)))


def _sabotage_variants(candidate, files):
    """name -> function(tree_dir) that damages the step's files in place."""
    py = [f for f in files if f.endswith(".py") and not TEST_FILE.search(f)]

    def delete(d):
        for f in files:
            p = os.path.join(d, f)
            if os.path.isfile(p):
                os.remove(p)

    def empty(d):
        for f in files:
            p = os.path.join(d, f)
            if os.path.isfile(p):
                open(p, "w").close()

    def stub_with(body):
        def apply(d):
            for f in py:
                p = os.path.join(d, f)
                if os.path.isfile(p):
                    with open(p) as fh:
                        src = fh.read()
                    with open(p, "w") as fh:
                        fh.write(_stub_source(src, body))

        return apply

    out = {"files deleted": delete, "files emptied": empty}
    if py:
        out["functions raise"] = stub_with("raise NotImplementedError")
        out["functions return None"] = stub_with("return None")
    return out


def vet(
    cmd,
    parent_tree,
    candidate_tree,
    step_files,
    *,
    worker_written=(),
    timeout=60.0,
    mutant_limit=12,
    min_kill=0.5,
):
    """Audit one plan check against one step. Trees are directories."""
    v = Vetting(status=REJECTED)
    v.reasons = policy_problems(cmd, step_files, worker_written)
    if v.reasons:
        return v
    with tempfile.TemporaryDirectory(prefix="urh-vet-") as tmp:
        cand = _copy(candidate_tree, os.path.join(tmp, "cand"))
        v.positive = _run(cmd, cand, timeout)
        if not v.positive:
            v.reasons.append("fails on the candidate")
            return v

        par = _copy(parent_tree, os.path.join(tmp, "parent"))
        v.vacuous = _run(cmd, par, timeout)
        if v.vacuous:
            v.reasons.append("passes on the state before the step (vacuous)")

        for name, damage in _sabotage_variants(candidate_tree, step_files).items():
            d = _copy(candidate_tree, os.path.join(tmp, "sab-" + name.replace(" ", "-")))
            damage(d)
            v.sabotage[name] = "pass" if _run(cmd, d, timeout) else "fail"
        survived = [k for k, r in v.sabotage.items() if r == "pass"]
        if survived:
            v.reasons.append("still passes when " + ", ".join(survived))
        if v.reasons:
            return v

        for f in [f for f in step_files if f.endswith(".py") and not TEST_FILE.search(f)]:
            path = os.path.join(candidate_tree, f)
            if not os.path.isfile(path):
                continue
            with open(path) as fh:
                src = fh.read()
            for i, (_, text) in enumerate(_mutants(src, limit=mutant_limit)):
                d = _copy(candidate_tree, os.path.join(tmp, "mut-%d-%d" % (len(f), i)))
                with open(os.path.join(d, f), "w") as fh:
                    fh.write(text)
                v.mutants_total += 1
                if not _run(cmd, d, timeout):
                    v.mutants_killed += 1
                shutil.rmtree(d, ignore_errors=True)
    if v.mutants_total and v.mutation_score < min_kill:
        v.status = WEAK
        v.reasons.append(
            "kills only %d of %d mutants of the step's code" % (v.mutants_killed, v.mutants_total)
        )
    else:
        v.status = TRUSTED
    return v


def gate_step(checks, parent_tree, candidate_tree, step_files, **kw):
    """Vet every plan check of a step; return (status, vettings).

    status is "pass" when every check passes on the candidate and at least one
    is trusted, "fail" when any check fails on the candidate, else "unsure".
    """
    vettings = {c: vet(c, parent_tree, candidate_tree, step_files, **kw) for c in checks}
    if any(not v.positive and not policy_problems(c, step_files) for c, v in vettings.items()):
        return "fail", vettings
    if checks and any(v.status == TRUSTED for v in vettings.values()):
        return "pass", vettings
    return "unsure", vettings
