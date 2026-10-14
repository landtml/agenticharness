import json

from urh.bench.judge_evalset import run
from urh.orchestrator import Harness, HarnessConfig
from urh.testing import ScriptedProvider


def test_evalset_scoring_and_blindness(tmp_path):
    root = tmp_path / "ev"
    (root / "tasks" / "t").mkdir(parents=True)
    (root / "tasks" / "t" / "spec.md").write_text("Write solution.py with f() returning 1.")
    (root / "corpus" / "t").mkdir(parents=True)
    (root / "corpus" / "t" / "broken_01.py").write_text("def f():\n    return 2\n")
    (root / "corpus" / "t" / "correct_01.py").write_text("def f():\n    return 1\n")
    (root / "labels.json").write_text(
        json.dumps(
            {
                "t/broken_01.py": {"label": "broken"},
                "t/correct_01.py": {"label": "correct"},
                "t/x.py": {"label": "ambiguous"},
            }
        )
    )
    judge = [
        {"verdict": "pass", "reasons": []},
        {"verdict": "pass", "reasons": []},
    ]  # a judge that accepts everything
    h = Harness(str(tmp_path / "h"), ScriptedProvider({"steps": {}, "judge": judge}), config=HarnessConfig())
    report = run(str(root), h, None, seed=0, workers=1)
    assert report["overall"]["broken"] == 1 and report["overall"]["false_accepts"] == 1
    assert report["overall"]["correct"] == 1 and report["overall"]["false_withholds"] == 0
    for call in h.journal.model_calls(h.journal.list_runs()[0].id):
        req = h.blobs.get_bytes(call["request_blob"]).decode()
        assert "broken_01" not in req and "correct_01" not in req  # file names never reach the judge
