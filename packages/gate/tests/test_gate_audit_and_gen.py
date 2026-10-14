import random
import unittest

import gate_helpers as helpers

from urh_gate import audit
from urh_gate import gen as g


class GenTest(unittest.TestCase):
    def test_draw_is_seeded(self):
        gen = g.lists(g.integers(-5, 5), 0, 10)
        a = [gen.draw(random.Random(1), 50) for _ in range(5)]
        b = [gen.draw(random.Random(1), 50) for _ in range(5)]
        self.assertEqual(a, b)

    def test_shrink_moves_towards_simpler(self):
        gen = g.lists(g.integers(-100, 100), 0, 10)
        for s in gen.shrink([50, -7, 3]):
            self.assertLessEqual(len(s), 3)
        self.assertIn([], gen.shrink([1, 2]))
        self.assertIn(0, g.integers(-10, 10).shrink(9))

    def test_edges_respect_bounds(self):
        for v in g.integers(3, 9).edges():
            self.assertTrue(3 <= v <= 9)
        for s in g.text("ab", 2, 4).edges():
            self.assertTrue(2 <= len(s) <= 4)


class AuditTest(unittest.TestCase):
    def test_mutants_differ_from_source(self):
        src = helpers.CORRECT
        ms = audit.mutants(src)
        self.assertGreater(len(ms), 5)
        self.assertTrue(all(text != src for _, text in ms))

    def test_practice_contract_audit(self):
        r = audit.audit(helpers.PRACTICE, helpers.PRACTICE_REF, workers=4, limit=20)
        self.assertEqual(r["reference"]["status"], "pass")
        self.assertEqual(r["vacuous"], [])
        self.assertEqual(r["mutants"]["gaps"], [])


if __name__ == "__main__":
    unittest.main()
