import os
import unittest

from gate_helpers import CORRECT, practice, workspace

from urh_gate import FAIL, PARK, PASS, Contract, FunctionSpec, Gate
from urh_gate import gen as g


class GateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.gate = Gate(practice())

    def verdict(self, src, **kw):
        return self.gate.evaluate(workspace(src), **kw)

    def test_reference_passes(self):
        v = self.verdict(CORRECT)
        self.assertEqual(v.status, PASS, v.reasons)
        for phase in ("examples", "edges", "random", "properties", "determinism"):
            self.assertIn(phase, v.phases)

    def test_missing_file_fails(self):
        v = self.gate.evaluate(workspace(None))
        self.assertEqual(v.status, FAIL)

    def test_non_utf8_fails(self):
        d = workspace(None)
        with open(os.path.join(d, "solution.py"), "wb") as fh:
            fh.write(b"\xff\xfe def")
        self.assertEqual(self.gate.evaluate(d).status, FAIL)

    def test_self_report_is_ignored(self):
        bad = "def dedupe(items, limit):\n    return list(dict.fromkeys(items))\n"
        self.assertEqual(self.verdict(bad, claimed="done, all tests pass").status, FAIL)
        v = self.verdict(CORRECT, claimed="I could not finish")
        self.assertEqual(v.status, PASS)
        self.assertEqual(v.claimed_by_worker, "I could not finish")

    def test_counterexample_is_shrunk(self):
        # Wrong only when limit is exactly 5: only random inputs find it.
        bad = CORRECT.replace("if limit < 0:", "if limit == 5:\n        limit = 4\n    if limit < 0:")
        v = self.verdict(bad)
        self.assertEqual(v.status, FAIL)
        ce = v.counterexample
        self.assertIsNotNone(ce)
        self.assertEqual(ce["args"][1], "5")
        # Shrinking should leave a short list (at most 5 distinct elements are needed).
        self.assertLessEqual(len(eval(ce["args"][0])), 6)

    def test_always_equal_object_fails(self):
        src = "class E(list):\n    def __eq__(s, o):\n        return True\ndef dedupe(items, limit):\n    return E()\n"
        v = self.verdict(src)
        self.assertEqual(v.status, FAIL)

    def test_input_mutation_fails(self):
        src = CORRECT.replace("seen, out = set(), []", "items.sort()\n    seen, out = set(), []")
        v = self.verdict(src)
        self.assertEqual(v.status, FAIL)

    def test_hash_order_dependence_fails(self):
        # Correct set, wrong order: depends on PYTHONHASHSEED, which differs between runs.
        src = "def dedupe(items, limit):\n    if limit < 0:\n        raise ValueError()\n    return list(set(items))[:limit]\n"
        v = self.verdict(src)
        self.assertEqual(v.status, FAIL)

    def test_state_across_calls_fails(self):
        src = (
            CORRECT
            + "\n_n = [0]\n_orig = dedupe\ndef dedupe(items, limit):\n    _n[0] += 1\n    r = _orig(items, limit)\n    return r if _n[0] < 200 else r[::-1]\n"
        )
        v = self.verdict(src)
        self.assertEqual(v.status, FAIL)

    def test_hard_exit_fails(self):
        self.assertEqual(self.verdict("import os\nos._exit(0)\n").status, FAIL)

    def test_hidden_example_hardcoding_fails(self):
        src = (
            "def dedupe(items, limit):\n    if items == ['b', 'a', 'b', 'c']:\n        return ['b', 'a']\n"
            "    if limit < 0:\n        raise ValueError()\n    return []\n"
        )
        self.assertEqual(self.verdict(src).status, FAIL)

    def test_verdict_replays_and_edits_reseed(self):
        a = self.verdict(CORRECT)
        b = self.verdict(CORRECT)
        c = self.verdict(CORRECT + "\n# edit\n")
        self.assertEqual((a.seed, a.status), (b.seed, b.status))
        self.assertNotEqual(a.seed, c.seed)

    def test_repair_note_has_no_paths(self):
        bad = "def dedupe(items, limit):\n    return list(dict.fromkeys(items))\n"
        note = self.verdict(bad).repair_note()
        self.assertIn("Smallest failing call", note)
        self.assertNotIn("/home", note)
        self.assertNotIn("/tmp", note)
        self.assertNotIn("contract", note.lower())

    def test_vacuous_contract_parks(self):
        c = Contract(name="vacuous", functions=[FunctionSpec("f", g.just([]))])
        v = Gate(c).evaluate(workspace("def f():\n    return 1\n"))
        self.assertEqual(v.status, PARK)

    def test_broken_reference_parks(self):
        def ref(x):
            raise KeyError("oracle bug")

        c = Contract(
            name="bad-oracle", functions=[FunctionSpec("f", g.tuples(g.integers(0, 3)), ref, random_cases=5)]
        )
        v = Gate(c).evaluate(workspace("def f(x):\n    return x\n"))
        self.assertEqual(v.status, PARK)
        self.assertIn("reference", v.reasons[0])

    def test_static_block_fails_before_running(self):
        v = self.verdict(CORRECT + "\nimport subprocess\n")
        self.assertEqual(v.status, FAIL)
        self.assertNotIn("examples", v.phases)

    def test_disable_for_ablation(self):
        bad = CORRECT.replace("if limit < 0:", "if limit == 5:\n        limit = 4\n    if limit < 0:")
        weak = Gate(practice(), disable=("edges", "random", "targeted", "properties", "determinism"))
        self.assertEqual(weak.evaluate(workspace(bad)).status, PASS)


if __name__ == "__main__":
    unittest.main()
