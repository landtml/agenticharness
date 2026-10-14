"""Blind evaluation of the gate against a labelled corpus.

Layout of an eval set::

    evalset/tasks/<task>/spec.md               what the worker sees
    evalset/tasks/<task>/hidden/contract.py    what the gate checks (never shown)
    evalset/corpus/<task>/*.py                 candidates written blind from spec.md
    evalset/corpus/<task>/manifest.json        the writer's intent per file
    evalset/labels.json                        ground truth (see ``label``)
    evalset/label_overrides.json               hand rulings on disputed labels

Ground truth does not come from the gate. ``label`` combines the writer's
stated intent with a deep differential run (many times the gate's random
budget, a different salt, no static policy), and every disagreement between
the two is listed for a human ruling in ``label_overrides.json``.
"""

import argparse
import json
import math
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor

from .contract import load_contract
from .gate import FAIL, PARK, PASS, Gate

# packages/gate: the evalset lives next to src/.
_PKG_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CONFIGS = {
    # The round-3 style gate: a person's hidden example tests and nothing else.
    "baseline-examples-only": {
        "disable": ("static", "edges", "random", "targeted", "properties", "determinism")
    },
    "full": {"disable": ()},
    "full-minus-static": {"disable": ("static",)},
    "full-minus-edges": {"disable": ("edges",)},
    "full-minus-random": {"disable": ("random",)},
    "full-minus-properties": {"disable": ("properties",)},
    "full-minus-targeted": {"disable": ("targeted",)},
    "full-minus-random-and-properties": {"disable": ("random", "properties")},
}


def wilson(k, n, z=1.96):
    """95% Wilson score interval for k successes out of n."""
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, centre - half), min(1.0, centre + half))


def _candidates(root):
    corpus = os.path.join(root, "corpus")
    for task in sorted(os.listdir(corpus)):
        man_path = os.path.join(corpus, task, "manifest.json")
        if not os.path.exists(man_path):
            continue
        with open(man_path) as fh:
            manifest = json.load(fh)
        for name in sorted(manifest):
            yield task, name, manifest[name]


def _contract_path(root, task):
    return os.path.join(root, "tasks", task, "hidden", "contract.py")


def _judge(job):
    root, task, name, kwargs = job
    contract = load_contract(_contract_path(root, task))
    with open(os.path.join(root, "corpus", task, name), "rb") as fh:
        src = fh.read()
    v = Gate(contract, **kwargs).evaluate_source(src)
    failed_phase = None
    if v.status == FAIL:
        failed_phase = next(
            (
                p
                for p in (
                    "load",
                    "static",
                    "examples",
                    "edges",
                    "random",
                    "targeted",
                    "properties",
                    "determinism",
                )
                if isinstance(v.phases.get(p), dict) and v.phases[p].get("failed")
            ),
            None,
        )
        if failed_phase is None:
            failed_phase = (
                "static"
                if v.phases.get("static", {}).get("blocking")
                else ("determinism" if "nondeterministic" in " ".join(v.reasons) else "load-or-import")
            )
    return task, name, v.status, failed_phase, v.reasons[:1]


def _pool_map(fn, jobs, workers):
    if workers <= 1:
        return [fn(j) for j in jobs]
    with ProcessPoolExecutor(workers) as ex:
        return list(ex.map(fn, jobs, chunksize=1))


SAFE_EVAL_BUILTINS = {"range": range, "str": str, "chr": chr, "list": list, "len": len, "int": int}


def _witness(job):
    """Does the candidate differ from the reference on the writer's exposing input?"""
    root, task, name, w = job
    from . import sandbox, values

    contract = load_contract(_contract_path(root, task))
    if "args_py" in w:
        args = eval(w["args_py"], {"__builtins__": SAFE_EVAL_BUILTINS})  # writer-supplied, tiny expression
    else:
        args = w["args"]
    spec = contract.function(w["fn"])
    try:
        expected = ("value", values.canon(spec.reference(*args)))
    except spec.error:
        expected = ("error", None)
    with open(os.path.join(root, "corpus", task, name)) as fh:
        src = fh.read()
    r = sandbox.run_program(src, [sandbox.call(w["fn"], *args)], per_call_timeout=5.0)
    if not r.ok or r.import_status != "ok" or not r.calls:
        return task, name, True
    c = r.calls[0]
    if "ok" in c:
        got = ("value", values.canon(values.decode(c["ok"])))
    elif c.get("value_error"):
        got = ("error", None)
    else:
        got = ("other", None)
    return task, name, got != expected or bool(c.get("mutated"))


# The labeller's own run: 25x the random budget, its own salt, and none of the
# phases (static policy, constant-guided inputs) that only the gate has.
LABEL_SETTINGS = {"salt": "labeler-deep-v1", "random_scale": 25, "disable": ("static", "targeted")}


def label(root, workers=4, scale=25):
    settings = dict(LABEL_SETTINGS, random_scale=scale)
    jobs = [(root, t, n, settings) for t, n, _ in _candidates(root)]
    deep = {(t, n): (st, r) for t, n, st, _, r in _pool_map(_judge, jobs, workers)}
    wjobs = [(root, t, n, m["witness"]) for t, n, m in _candidates(root) if "witness" in m]
    exposed = {(t, n): e for t, n, e in _pool_map(_witness, wjobs, workers)}
    overrides = {}
    opath = os.path.join(root, "label_overrides.json")
    if os.path.exists(opath):
        with open(opath) as fh:
            overrides = json.load(fh)
    labels, disputes = {}, []
    for t, n, meta in _candidates(root):
        key = f"{t}/{n}"
        intent = meta.get("intent")
        st, reasons = deep[(t, n)]
        functional = "correct" if st == PASS else "broken"
        if exposed.get((t, n)):
            functional = "broken"  # the writer's witness input shows a spec violation
        if key in overrides:
            lab, source = overrides[key]["label"], "override: " + overrides[key]["why"]
        elif intent == "gaming":
            lab, source = "broken", "gaming intent"
        elif intent == functional:
            lab, source = functional, "intent and deep differential agree"
        else:
            lab, source = functional, f"DISPUTED: intent {intent}, deep differential {functional}"
            disputes.append({"candidate": key, "intent": intent, "deep": functional, "deep_reason": reasons})
        labels[key] = {
            "label": lab,
            "intent": intent,
            "deep": "correct" if st == PASS else "broken",
            "witness_exposes": exposed.get((t, n)),
            "source": source,
        }
    with open(os.path.join(root, "labels.json"), "w") as fh:
        json.dump(labels, fh, indent=1, sort_keys=True)
    return labels, disputes


def run(root, configs=None, workers=4):
    with open(os.path.join(root, "labels.json")) as fh:
        labels = json.load(fh)
    results = {}
    for cname in configs or list(CONFIGS):
        kwargs = CONFIGS[cname]
        t0 = time.time()
        jobs = [
            (root, t, n, kwargs)
            for t, n, _ in _candidates(root)
            if labels.get(f"{t}/{n}", {}).get("label") in ("correct", "broken")
        ]
        rows = _pool_map(_judge, jobs, workers)
        neg = [r for r in rows if labels[f"{r[0]}/{r[1]}"]["label"] == "broken"]
        pos = [r for r in rows if labels[f"{r[0]}/{r[1]}"]["label"] == "correct"]
        fa = [r for r in neg if r[2] == PASS]
        fw = [r for r in pos if r[2] != PASS]
        fam = {}
        meta = {(t, n): m for t, n, m in _candidates(root)}
        for r in neg:
            f = meta[(r[0], r[1])].get("family", "blind")
            d = fam.setdefault(f, {"negatives": 0, "false_accepts": 0})
            d["negatives"] += 1
            d["false_accepts"] += r[2] == PASS
        for d in fam.values():
            d["ci95"] = wilson(d["false_accepts"], d["negatives"])
        caught_by = {}
        for r in neg:
            if r[2] == FAIL:
                caught_by[r[3]] = caught_by.get(r[3], 0) + 1
        results[cname] = {
            "negatives": len(neg),
            "positives": len(pos),
            "false_accepts": len(fa),
            "false_accept_rate": len(fa) / max(1, len(neg)),
            "false_accept_ci95": wilson(len(fa), len(neg)),
            "false_withholds": len(fw),
            "false_withhold_rate": len(fw) / max(1, len(pos)),
            "false_withhold_ci95": wilson(len(fw), len(pos)),
            "parks": sum(1 for r in rows if r[2] == PARK),
            "accepted_broken": [f"{r[0]}/{r[1]}" for r in fa],
            "withheld_correct": [f"{r[0]}/{r[1]}: {r[4]}" for r in fw],
            "caught_by_phase": caught_by,
            "by_family": fam,
            "seconds": round(time.time() - t0, 1),
        }
    return results


def render_markdown(results, labels):
    lines = [
        "# Gate evaluation results",
        "",
        "Generated by `python -m urh_gate.evaluate run`. Rates are per candidate; intervals are 95% Wilson.",
        "",
    ]
    n_neg = sum(1 for v in labels.values() if v["label"] == "broken")
    n_pos = sum(1 for v in labels.values() if v["label"] == "correct")
    lines += [
        "Corpus: %d labelled candidates (%d broken or gaming, %d correct) across %d tasks."
        % (n_neg + n_pos, n_neg, n_pos, len({k.split("/")[0] for k in labels})),
        "",
    ]
    lines += [
        "| Gate configuration | False accepts | Rate (95% CI) | False withholds | Rate (95% CI) | Parks |",
        "|---|---|---|---|---|---|",
    ]
    for name, r in results.items():
        lines.append(
            "| %s | %d / %d | %.1f%% (%.1f–%.1f%%) | %d / %d | %.1f%% (%.1f–%.1f%%) | %d |"
            % (
                name,
                r["false_accepts"],
                r["negatives"],
                100 * r["false_accept_rate"],
                100 * r["false_accept_ci95"][0],
                100 * r["false_accept_ci95"][1],
                r["false_withholds"],
                r["positives"],
                100 * r["false_withhold_rate"],
                100 * r["false_withhold_ci95"][0],
                100 * r["false_withhold_ci95"][1],
                r["parks"],
            )
        )
    lines += [
        "",
        "## False accepts by corpus family",
        "",
        "| Gate configuration | " + " | ".join(sorted(next(iter(results.values()))["by_family"])) + " |",
        "|---|" + "---|" * len(next(iter(results.values()))["by_family"]),
    ]
    for name, r in results.items():
        cells = []
        for f in sorted(r["by_family"]):
            d = r["by_family"][f]
            cells.append(
                "%d / %d (CI %.1f–%.1f%%)"
                % (d["false_accepts"], d["negatives"], 100 * d["ci95"][0], 100 * d["ci95"][1])
            )
        lines.append("| {} | {} |".format(name, " | ".join(cells)))
    full = results.get("full")
    if full:
        lines += ["", "## Full gate: which phase caught each broken candidate", ""]
        for phase, n in sorted(full["caught_by_phase"].items(), key=lambda kv: -kv[1]):
            lines.append("- %s: %d" % (phase, n))
        lines += ["", "## Accepted broken candidates (full gate)", ""]
        lines += ["- " + c for c in full["accepted_broken"]] or ["- none"]
        lines += ["", "## Withheld correct candidates (full gate)", ""]
        lines += ["- " + c for c in full["withheld_correct"]] or ["- none"]
    return "\n".join(lines) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m urh_gate.evaluate")
    ap.add_argument("command", choices=["label", "run"])
    ap.add_argument("--root", default=os.path.join(_PKG_ROOT, "evalset"))
    ap.add_argument("--workers", type=int, default=os.cpu_count() or 2)
    ap.add_argument("--configs", nargs="*")
    args = ap.parse_args(argv)
    if args.command == "label":
        labels, disputes = label(args.root, args.workers)
        print(json.dumps({"labelled": len(labels), "disputes": disputes}, indent=1))
        return 0
    results = run(args.root, args.configs, args.workers)
    with open(os.path.join(args.root, "labels.json")) as fh:
        labels = json.load(fh)
    with open(os.path.join(args.root, "results.json"), "w") as fh:
        json.dump(results, fh, indent=1, sort_keys=True)
    md = render_markdown(results, labels)
    with open(os.path.join(args.root, "RESULTS.md"), "w") as fh:
        fh.write(md)
    print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
