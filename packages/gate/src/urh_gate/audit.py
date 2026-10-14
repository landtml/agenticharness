"""Self-audit of a contract: is this gate able to refuse anything?

Three checks, all run through the real gate:

1. Reference: the contract's own reference solution must pass. A failure
   means the gate would withhold correct work.
2. Stub battery: trivial non-solutions (return None, echo the input, always
   raise, constants, an empty file) must all fail. One that passes marks the
   contract vacuous for that function.
3. Mutation testing: single-site AST mutants of the reference must fail.
   Survivors are re-run under a deep differential (many more inputs, another
   salt); a survivor the deep run kills is a real gap in the gate, one it
   cannot kill is reported as probably equivalent.

The report gives the mutation score with equivalents removed, and lists every
real gap with the mutated line so the contract author can add a case.
"""

import argparse
import ast
import copy
import json
import os
import random
import sys
from concurrent.futures import ProcessPoolExecutor

from .contract import load_contract
from .gate import PASS, Gate

STUB_BODIES = {
    "returns None": "return None",
    "echoes first argument": "return args[0] if args else None",
    "always raises ValueError": "raise ValueError('stub')",
    "returns 0": "return 0",
    "returns empty string": "return ''",
    "returns empty list": "return []",
    "returns True": "return True",
}


def stub_sources(contract):
    names = [f.name for f in contract.functions]
    out = {"empty file": ""}
    for label, body in STUB_BODIES.items():
        out[label] = "".join(f"def {n}(*args, **kwargs):\n    {body}\n\n" for n in names)
    for i, ex in enumerate(contract.examples[:3]):
        if not ex.raises:
            out["constant from hidden example %d" % i] = "".join(
                f"def {n}(*args, **kwargs):\n    return {ex.expect!r}\n\n" for n in names
            )
    return out


class _Mutator(ast.NodeTransformer):
    """Applies the mutation at one site index; counts sites when target is None."""

    CMP_SWAP = {
        ast.Lt: ast.LtE,
        ast.LtE: ast.Lt,
        ast.Gt: ast.GtE,
        ast.GtE: ast.Gt,
        ast.Eq: ast.NotEq,
        ast.NotEq: ast.Eq,
        ast.In: ast.NotIn,
        ast.NotIn: ast.In,
        ast.Is: ast.IsNot,
        ast.IsNot: ast.Is,
    }
    BIN_SWAP = {
        ast.Add: ast.Sub,
        ast.Sub: ast.Add,
        ast.Mult: ast.FloorDiv,
        ast.FloorDiv: ast.Mult,
        ast.Mod: ast.FloorDiv,
        ast.Div: ast.Mult,
    }

    def __init__(self, target=None):
        self.target = target
        self.count = 0
        self.description = None

    def _hit(self, node, desc):
        idx = self.count
        self.count += 1
        if idx == self.target:
            self.description = "line %d: %s" % (getattr(node, "lineno", 0), desc)
            return True
        return False

    def visit_Compare(self, node):
        self.generic_visit(node)
        for i, op in enumerate(node.ops):
            new = self.CMP_SWAP.get(type(op))
            if new and self._hit(node, f"{type(op).__name__} -> {new.__name__}"):
                node.ops[i] = new()
        return node

    def visit_BinOp(self, node):
        self.generic_visit(node)
        new = self.BIN_SWAP.get(type(node.op))
        if new and self._hit(node, f"{type(node.op).__name__} -> {new.__name__}"):
            node.op = new()
        return node

    def visit_BoolOp(self, node):
        self.generic_visit(node)
        if self._hit(node, "and <-> or"):
            node.op = ast.Or() if isinstance(node.op, ast.And) else ast.And()
        return node

    def visit_UnaryOp(self, node):
        self.generic_visit(node)
        if isinstance(node.op, ast.Not) and self._hit(node, "drop not"):
            return node.operand
        return node

    def visit_Constant(self, node):
        if type(node.value) is int:
            if self._hit(node, "%d -> %d" % (node.value, node.value + 1)):
                return ast.copy_location(ast.Constant(node.value + 1), node)
            if self._hit(node, "%d -> %d" % (node.value, node.value - 1)):
                return ast.copy_location(ast.Constant(node.value - 1), node)
        elif type(node.value) is str and node.value and len(node.value) <= 12:
            if self._hit(node, f"string {node.value!r} -> {node.value[:-1]!r}"):
                return ast.copy_location(ast.Constant(node.value[:-1]), node)
        return node

    def _stmts(self, body):
        out = []
        for stmt in body:
            if isinstance(stmt, (ast.FunctionDef, ast.ClassDef, ast.Import, ast.ImportFrom)):
                out.append(stmt)
                continue
            if self._hit(stmt, f"delete statement `{ast.unparse(stmt).splitlines()[0][:60]}`"):
                out.append(ast.copy_location(ast.Pass(), stmt))
            else:
                out.append(stmt)
        return out

    def generic_visit(self, node):
        for field in ("body", "orelse", "finalbody"):
            if (
                isinstance(getattr(node, field, None), list)
                and not isinstance(node, ast.Module)
                and getattr(node, field)
                and isinstance(getattr(node, field)[0], ast.stmt)
            ):
                setattr(node, field, self._stmts(getattr(node, field)))
        return super().generic_visit(node)


def mutants(source, limit=150, seed=0):
    tree = ast.parse(source)
    counter = _Mutator()
    counter.visit(copy.deepcopy(tree))
    sites = list(range(counter.count))
    if len(sites) > limit:
        sites = sorted(random.Random(seed).sample(sites, limit))
    out = []
    for i in sites:
        m = _Mutator(target=i)
        new = m.visit(copy.deepcopy(tree))
        ast.fix_missing_locations(new)
        try:
            text = ast.unparse(new)
        except Exception:
            continue
        if text != ast.unparse(tree):
            out.append((m.description, text))
    return out


def _gate_job(job):
    contract_path, source, kwargs = job
    v = Gate(load_contract(contract_path), **kwargs).evaluate_source(source)
    return v.status, v.reasons[:1]


def audit(contract_path, reference_path, workers=4, limit=150):
    contract = load_contract(contract_path)
    with open(reference_path) as fh:
        ref_src = fh.read()
    report = {"contract": contract.name}

    ref_status, ref_reasons = _gate_job((contract_path, ref_src, {}))
    report["reference"] = {"status": ref_status, "reasons": ref_reasons}

    stubs = stub_sources(contract)
    jobs = [(contract_path, src, {}) for src in stubs.values()]
    with ProcessPoolExecutor(workers) as ex:
        stub_res = list(ex.map(_gate_job, jobs))
    report["stubs"] = {name: st for name, (st, _) in zip(stubs, stub_res, strict=False)}
    report["vacuous"] = [name for name, (st, _) in zip(stubs, stub_res, strict=False) if st == PASS]

    muts = mutants(ref_src, limit=limit)
    with ProcessPoolExecutor(workers) as ex:
        first = list(ex.map(_gate_job, [(contract_path, src, {}) for _, src in muts]))
        survivors = [i for i, (st, _) in enumerate(first) if st == PASS]
        deep = list(
            ex.map(
                _gate_job,
                [
                    (
                        contract_path,
                        muts[i][1],
                        {"salt": "audit-deep-v1", "random_scale": 25, "disable": ("static",)},
                    )
                    for i in survivors
                ],
            )
        )
    gaps = [muts[i][0] for i, (st, _) in zip(survivors, deep, strict=False) if st != PASS]
    equivalent = [muts[i][0] for i, (st, _) in zip(survivors, deep, strict=False) if st == PASS]
    killed = len(muts) - len(survivors)
    denom = len(muts) - len(equivalent)
    report["mutants"] = {
        "total": len(muts),
        "killed": killed,
        "probably_equivalent": len(equivalent),
        "gaps": gaps,
        "score": (killed / denom) if denom else 1.0,
        "equivalent_examples": equivalent[:10],
    }
    return report


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m urh_gate.audit")
    ap.add_argument(
        "task_dirs", nargs="+", help="task directories containing hidden/contract.py and hidden/reference.py"
    )
    ap.add_argument("--workers", type=int, default=os.cpu_count() or 2)
    ap.add_argument("--limit", type=int, default=150)
    ap.add_argument("--out")
    args = ap.parse_args(argv)
    reports = []
    for d in args.task_dirs:
        r = audit(
            os.path.join(d, "hidden", "contract.py"),
            os.path.join(d, "hidden", "reference.py"),
            args.workers,
            args.limit,
        )
        m = r["mutants"]
        print(
            "%-16s reference=%s vacuous=%s mutants=%d killed=%d equivalent=%d gaps=%d score=%.3f"
            % (
                r["contract"],
                r["reference"]["status"],
                r["vacuous"] or "none",
                m["total"],
                m["killed"],
                m["probably_equivalent"],
                len(m["gaps"]),
                m["score"],
            )
        )
        for gap in m["gaps"]:
            print("    gap: " + gap)
        reports.append(r)
    if args.out:
        with open(args.out, "w") as fh:
            json.dump(reports, fh, indent=1)
    bad = any(r["reference"]["status"] != PASS or r["vacuous"] for r in reports)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
