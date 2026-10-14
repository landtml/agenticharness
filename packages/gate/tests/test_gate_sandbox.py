import unittest

from urh_gate import sandbox as sb


def run(src, *calls, **kw):
    return sb.run_program(src, list(calls), per_call_timeout=kw.pop("t", 0.5), **kw)


class SandboxTest(unittest.TestCase):
    def test_plain_call(self):
        r = run("def f(x):\n    return x + 1\n", sb.call("f", 1))
        self.assertTrue(r.ok)
        self.assertEqual(r.calls[0]["ok"], ["i", "2"])

    def test_value_error_reported(self):
        r = run("def f():\n    raise ValueError('no')\n", sb.call("f"))
        self.assertTrue(r.calls[0]["value_error"])

    def test_file_open_denied_and_recorded(self):
        r = run(
            "def f():\n    try:\n        return open('/etc/hostname').read()\n    except Exception:\n        return 'x'\n",
            sb.call("f"),
        )
        self.assertEqual(r.calls[0]["ok"], ["s", "x"])
        self.assertTrue(any(v.startswith("open") for v in r.violations))

    def test_fresh_import_denied(self):
        r = run("import subprocess\n")
        self.assertTrue(r.import_status.startswith("error"))
        self.assertIn("import subprocess", r.violations)

    def test_hidden_module_cannot_be_reimported(self):
        r = run("import signal\n")
        self.assertIn("import signal", r.violations)

    def test_frame_walk_denied(self):
        r = run("import sys\ndef f():\n    return sys._getframe(1).f_code.co_name\n", sb.call("f"))
        self.assertIn("sys._getframe", r.violations)

    def test_hard_exit_gives_no_report(self):
        r = run("import os\nos._exit(0)\n")
        self.assertFalse(r.ok)

    def test_sys_exit_is_an_import_error(self):
        r = run("import sys\nsys.exit(0)\n")
        self.assertEqual(r.import_status, "error:SystemExit")

    def test_writing_to_report_channel_is_tampering(self):
        src = "import os\nfor fd in range(3, 12):\n    try:\n        os.write(fd, b'URHGATE1 x 2\\n{}')\n    except OSError:\n        pass\ndef f():\n    return 1\n"
        r = run(src, sb.call("f"))
        self.assertFalse(r.ok)

    def test_timeout_stops_program(self):
        r = run(
            "def f():\n    while True:\n        pass\ndef g():\n    return 1\n",
            sb.call("f"),
            sb.call("g"),
            t=0.2,
        )
        self.assertTrue(r.calls[0].get("timeout"))
        self.assertTrue(r.calls[1].get("skipped"))

    def test_swallowed_timeout_hits_wall_clock(self):
        src = "def f():\n    while True:\n        try:\n            while True:\n                pass\n        except BaseException:\n            pass\n"
        r = sb.run_program(src, [sb.call("f")], per_call_timeout=0.2, wall_timeout=3)
        self.assertFalse(r.ok)

    def test_mutation_detected(self):
        r = run("def f(x):\n    x.append(1)\n    return 0\n", sb.call("f", [1]))
        self.assertTrue(r.calls[0].get("mutated"))

    def test_refs_chain_calls(self):
        r = sb.run_program(
            "def f(x):\n    return x * 2\n", [sb.call("f", 2), {"fn": "f", "args": [sb.ref(0)]}]
        )
        self.assertEqual(r.calls[1]["ok"], ["i", "8"])

    def test_bad_output_type(self):
        r = run(
            "class E(int):\n    def __eq__(s, o):\n        return True\ndef f():\n    return E(1)\n",
            sb.call("f"),
        )
        self.assertIn("bad", r.calls[0])

    def test_memory_limit(self):
        r = sb.run_program("def f():\n    return len('x' * (1 << 32))\n", [sb.call("f")], mem_bytes=256 << 20)
        self.assertTrue(r.ok)
        self.assertEqual(r.calls[0].get("raise"), "MemoryError")


if __name__ == "__main__":
    unittest.main()
