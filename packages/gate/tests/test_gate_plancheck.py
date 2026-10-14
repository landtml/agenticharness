import os
import tempfile
import unittest

from urh_gate import plancheck as pc

CODE = "def f(x):\n    if x < 0:\n        raise ValueError\n    return x * 2 + 1\n"


class PlanCheckTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.parent = tempfile.mkdtemp()
        cls.cand = tempfile.mkdtemp()
        with open(os.path.join(cls.cand, "m.py"), "w") as fh:
            fh.write(CODE)
        with open(os.path.join(cls.cand, "test_m.py"), "w") as fh:
            fh.write("def test():\n    assert True\n")
        cls.files = ["m.py", "test_m.py"]

    def vet(self, cmd):
        return pc.vet(cmd, self.parent, self.cand, self.files, mutant_limit=8)

    def test_behavioural_check_is_trusted(self):
        v = self.vet('python3 -c "from m import f; assert f(2) == 5 and f(0) == 1"')
        self.assertEqual(v.status, pc.TRUSTED, v.reasons)
        self.assertGreater(v.mutants_killed, 0)

    def test_import_only_is_rejected_by_sabotage(self):
        v = self.vet('python3 -c "import m"')
        self.assertEqual(v.status, pc.REJECTED)
        self.assertEqual(v.sabotage["functions return None"], "pass")

    def test_static_policy(self):
        for cmd in [
            "true",
            "test -f m.py",
            "python3 -m pytest -q test_m.py",
            'python3 -c "from m import f; assert f(2) == 5" || true',
            "curl http://x",
        ]:
            self.assertEqual(self.vet(cmd).status, pc.REJECTED, cmd)

    def test_loose_assertion_is_weak(self):
        v = self.vet('python3 -c "from m import f; assert f(3) > 0"')
        self.assertEqual(v.status, pc.WEAK)

    def test_vacuous_check_rejected(self):
        os.makedirs(os.path.join(self.parent, "x"), exist_ok=True)
        with open(os.path.join(self.parent, "m.py"), "w") as fh:
            fh.write(CODE)
        try:
            v = self.vet('python3 -c "from m import f; assert f(2) == 5"')
            self.assertTrue(v.vacuous)
            self.assertEqual(v.status, pc.REJECTED)
        finally:
            os.remove(os.path.join(self.parent, "m.py"))

    def test_gate_step(self):
        good = 'python3 -c "from m import f; assert f(2) == 5 and f(0) == 1"'
        status, _ = pc.gate_step([good], self.parent, self.cand, self.files, mutant_limit=6)
        self.assertEqual(status, "pass")
        status, _ = pc.gate_step(['python3 -c "import m"'], self.parent, self.cand, self.files)
        self.assertEqual(status, "unsure")
        status, _ = pc.gate_step(
            [good, 'python3 -c "from m import f; assert f(2) == 6"'],
            self.parent,
            self.cand,
            self.files,
            mutant_limit=6,
        )
        self.assertEqual(status, "fail")


if __name__ == "__main__":
    unittest.main()
