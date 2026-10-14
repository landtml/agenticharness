import itertools
import json
import shutil
import sys
from pathlib import Path

import pytest

from urh.checkpoint import GitCheckpoint
from urh.gate import ScriptGate, audit_gate
from urh.spec import Check, GateSpec, StepSpec

PY = sys.executable
ADD_OK = "def add(a, b):\n    return a + b\n"
ADD_BAD = "def add(a, b):\n    return a - b\n"
TEST_X = "from add import add\n\ndef test_add():\n    assert add(2, 3) == 5\n"
CHECK = Check(name="add", cmd=[PY, "-m", "pytest", "-q", "-p", "no:cacheprovider", "_hidden/test_x.py"])


@pytest.fixture
def hidden(tmp_path):
    d = tmp_path / "hidden"
    d.mkdir()
    (d / "test_x.py").write_text(TEST_X)
    return str(d)


@pytest.fixture
def ckpt(tmp_path):
    seed = tmp_path / "seed"
    seed.mkdir()
    (seed / "README.md").write_text("seed\n")
    c = GitCheckpoint(str(tmp_path / "run"))
    c.init(str(seed))
    return c


def _candidate(ckpt, root, epoch, files: dict[str, str]) -> str:
    ws = ckpt.prepare_workspace(epoch, root)
    for name, body in files.items():
        p = Path(ws, name)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body)
    _, commit = ckpt.snapshot(epoch, root, f"epoch {epoch}")
    return commit


def _gate(hidden: str) -> ScriptGate:
    return ScriptGate(GateSpec(checks=[CHECK], hidden_dir=hidden, protected=["_hidden/"]))


STEP = StepSpec(title="add", instructions="write add", files=["add.py"])


def test_correct_artifact_passes(ckpt, hidden):
    root = ckpt.verified_head()
    commit = _candidate(ckpt, root, 1, {"add.py": ADD_OK})
    assert _gate(hidden).evaluate(ckpt, root, commit, STEP).status == "pass"


def test_broken_artifact_fails_without_leaking_paths(tmp_path, ckpt, hidden):
    root = ckpt.verified_head()
    commit = _candidate(ckpt, root, 1, {"add.py": ADD_BAD})
    v = _gate(hidden).evaluate(ckpt, root, commit, STEP)
    assert v.status == "fail"
    assert any("test_x.py" in f for f in v.failures)
    assert str(tmp_path) not in json.dumps(v.to_dict())


def test_missing_expected_file_fails(ckpt, hidden):
    root = ckpt.verified_head()
    commit = _candidate(ckpt, root, 1, {"other.py": "x = 1\n"})
    v = _gate(hidden).evaluate(ckpt, root, commit, STEP)
    assert v.status == "fail"
    assert "missing file: add.py" in v.failures


def test_no_matching_check_is_unsure(ckpt, hidden):
    root = ckpt.verified_head()
    commit = _candidate(ckpt, root, 1, {"add.py": ADD_OK})
    step = StepSpec(title="add", instructions="write add", files=["add.py"], checks=["nonexistent"])
    assert _gate(hidden).evaluate(ckpt, root, commit, step).status == "unsure"


def test_candidate_touching_protected_path_fails(ckpt, hidden):
    root = ckpt.verified_head()
    commit = _candidate(ckpt, root, 1, {"add.py": ADD_OK, "_hidden/test_x.py": "def test_x():\n    pass\n"})
    assert _gate(hidden).evaluate(ckpt, root, commit, STEP).status == "fail"


def test_audit_gate_accepts_no_broken_mutant(tmp_path, ckpt, hidden):
    root = ckpt.verified_head()
    bodies = {
        "sub": ADD_BAD,
        "zero": "def add(a, b):\n    return 0\n",
        "none": "def add(a, b):\n    return None\n",
    }
    mutants = {}
    for name, body in bodies.items():
        d = tmp_path / "mutants" / name
        d.mkdir(parents=True)
        (d / "add.py").write_text(body)
        mutants[name] = str(d)

    epochs = itertools.count(10)

    def snapshot_dir(path: str) -> str:
        epoch = next(epochs)
        ws = ckpt.prepare_workspace(epoch, root)
        shutil.copytree(path, ws, dirs_exist_ok=True)
        _, commit = ckpt.snapshot(epoch, root, f"mutant {epoch}")
        return commit

    report = audit_gate(_gate(hidden), ckpt, root, mutants, STEP, snapshot_dir)
    assert report["mutants"] == 3
    assert report["accepted"] == []
    assert report["false_accept_rate"] == 0.0
