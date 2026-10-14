"""The gate as a check command for the harness's script gate.

The script gate copies hidden checks into the exported tree as ``_hidden`` and
runs each check command there; exit code 0 means pass. This test runs the
contract gate exactly that way.
"""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.dirname(HERE)
SLUG = os.path.join(PKG, "crosscheck", "slug", "hidden")

REFERENCE = """import re
import unicodedata


def slugify(text):
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
"""
# Passes every example in the step instructions but keeps underscores.
UNDERSCORE = REFERENCE.replace("[^a-z0-9]+", "[^a-z0-9_]+")


def check(source):
    tree = tempfile.mkdtemp(prefix="urh-tree-")
    try:
        with open(os.path.join(tree, "slug.py"), "w") as fh:
            fh.write(source)
        shutil.copytree(SLUG, os.path.join(tree, "_hidden"))
        env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": tree,
            "PYTHONPATH": os.path.join(PKG, "src"),
            "URH_GATE_SALT": "integration-test",
        }
        cmd = [
            sys.executable,
            "-m",
            "urh_gate",
            "check",
            "--contract",
            "_hidden/contract.py",
            "--workspace",
            ".",
        ]
        return subprocess.run(cmd, cwd=tree, env=env, capture_output=True, text=True, timeout=300)
    finally:
        shutil.rmtree(tree, ignore_errors=True)


class CheckCommandTest(unittest.TestCase):
    def test_reference_passes(self):
        r = check(REFERENCE)
        self.assertEqual(r.returncode, 0, r.stdout[-500:])

    def test_example_passing_bug_fails_with_path_free_note(self):
        r = check(UNDERSCORE)
        self.assertEqual(r.returncode, 1)
        self.assertNotIn("_hidden", r.stdout)
        self.assertIn('"status": "fail"', r.stdout)


if __name__ == "__main__":
    unittest.main()
