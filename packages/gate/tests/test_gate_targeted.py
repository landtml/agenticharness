import random
import unittest

from urh_gate import targeted


class HarvestTest(unittest.TestCase):
    def test_constant_expressions_are_folded(self):
        src = 'A = len("abcdefg")\nB = chr(sum((3, 4)))\nC = len("abcdefghij") ** 3\n'
        ints, strs = targeted.harvest(src)
        self.assertIn(7, ints)
        self.assertIn(1000, ints)
        self.assertIn(1001, ints)  # powers also give their neighbours
        self.assertIn("\x07", strs)

    def test_harvest_ignores_huge_and_broken_source(self):
        self.assertEqual(targeted.harvest("def f(:"), ([], []))
        ints, _ = targeted.harvest("X = 10 ** 400\n")
        self.assertNotIn(10**400, ints)


class VariantTest(unittest.TestCase):
    def test_limit_and_room_to_exceed_it(self):
        src = "def f(capacity, keys):\n    slots = min(capacity, 2048)\n"
        out = targeted.variants([[2, ["a", "b", "c"]]], src, random.Random(1), budget=5000)
        self.assertTrue(any(v[0] > 2048 and len(set(v[1])) > v[0] for v in out))

    def test_near_twins_for_comparisons(self):
        out = targeted.variants([["1.0.0-rc.1+b.2", "1.0.0"]], "", random.Random(1), budget=5000)
        self.assertIn(["1.0.0-rc.1+b.2", "1.0.0-rc.1+b.3"], out)
        self.assertIn(["1.0.0-rc.1+b.2", "1.0.0-rc.1"], out)


if __name__ == "__main__":
    unittest.main()


class ExhaustiveTest(unittest.TestCase):
    def test_small_domain_is_run_whole(self):
        from urh_gate import Contract, FunctionSpec, Gate
        from urh_gate import gen as g

        def square(n):
            return n * n

        spec = FunctionSpec("f", g.tuples(g.integers(0, 5000)), square, random_cases=5)
        bad = "def f(n):\n    return n * n + (n == sum((4000, 321)))\n"
        loose = Contract(name="sq", functions=[spec])
        self.assertEqual(
            Gate(loose, salt="t", disable=("targeted",)).evaluate_source(bad.encode()).status, "pass"
        )
        spec.exhaustive = lambda: [[n] for n in range(5001)]
        tight = Contract(name="sq", functions=[spec])
        self.assertEqual(
            Gate(tight, salt="t", disable=("targeted",)).evaluate_source(bad.encode()).status, "fail"
        )
