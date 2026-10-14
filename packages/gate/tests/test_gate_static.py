import unittest

from urh_gate import static
from urh_gate.contract import DEFAULT_ALLOWED_IMPORTS


def blocks(src):
    return [f.rule for f in static.scan(src, DEFAULT_ALLOWED_IMPORTS) if f.level == "block"]


class StaticTest(unittest.TestCase):
    def test_clean_code_passes(self):
        src = (
            "import re\nimport os\nfrom collections import OrderedDict\n"
            "def f(s, l):\n    l.remove(1)\n    return s.replace('a', 'b'), os.path.join('a', 'b')\n"
        )
        self.assertEqual(blocks(src), [])

    def test_blocks(self):
        cases = {
            "import subprocess": "import",
            "from os import system": "import-name",
            "import os as o\no.system('x')": "attr",
            "import sys\nsys.modules": "attr",
            "open('x')": "call",
            "eval('1')": "call",
            "__import__('os')": "call",
            "x = ().__class__.__bases__": "attr",
            "import builtins\nbuiltins.len = None": "monkeypatch",
            "import sys\nsetattr(sys, 'x', 1)": "monkeypatch",
            "getattr(object, '__subclasses__')": "getattr",
            "import os\ny = os\ny.system('x')": "attr",
        }
        for src, rule in cases.items():
            self.assertIn(rule, blocks(src), src)

    def test_warnings_do_not_block(self):
        src = "class E:\n    def __eq__(s, o):\n        return True\ntry:\n    pass\nexcept:\n    pass\n"
        findings = static.scan(src, DEFAULT_ALLOWED_IMPORTS)
        self.assertTrue(findings)
        self.assertTrue(all(f.level == "warn" for f in findings))

    def test_syntax_error_blocks(self):
        self.assertEqual(blocks("def ("), ["syntax"])


if __name__ == "__main__":
    unittest.main()
