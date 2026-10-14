import os
from pathlib import Path

import pytest

from urh.checkpoint import CheckpointError, GitCheckpoint


@pytest.fixture
def seed(tmp_path):
    d = tmp_path / "seed"
    (d / "pkg").mkdir(parents=True)
    (d / "README.md").write_text("hello\n")
    (d / "pkg" / "a.py").write_text("A = 1\n")
    return str(d)


@pytest.fixture
def ckpt(tmp_path, seed):
    c = GitCheckpoint(str(tmp_path / "run"))
    c.init(seed)
    return c


def _files(ckpt, commit, dest: Path) -> list[str]:
    ckpt.export(commit, str(dest))
    return sorted(p.relative_to(dest).as_posix() for p in dest.rglob("*") if p.is_file())


def test_init_seeds_verified_commit_with_seed_files(tmp_path, seed):
    c = GitCheckpoint(str(tmp_path / "run"))
    root = c.init(seed)
    assert c.verified_head() == root
    assert _files(c, root, tmp_path / "export") == ["README.md", "pkg/a.py"]


def test_init_is_idempotent(tmp_path, seed):
    c = GitCheckpoint(str(tmp_path / "run"))
    root = c.init(seed)
    assert c.init(seed) == root
    assert c.verified_head() == root


def test_prepare_snapshot_and_promote(ckpt):
    root = ckpt.verified_head()
    ws = ckpt.prepare_workspace(1, root)
    assert Path(ws, "pkg", "a.py").read_text() == "A = 1\n"

    Path(ws, "new.py").write_text("X = 2\n")
    _, commit = ckpt.snapshot(1, root, "step 1")
    assert "new.py" in ckpt.changed_paths(root, commit)
    assert ckpt.verified_head() == root  # a snapshot is not yet verified

    ckpt.promote(commit, root)
    assert ckpt.verified_head() == commit


def test_promote_rejects_wrong_expected_parent(ckpt):
    root = ckpt.verified_head()
    ws = ckpt.prepare_workspace(1, root)
    Path(ws, "a.txt").write_text("1")
    _, first = ckpt.snapshot(1, root, "first")
    ckpt.promote(first, root)

    Path(ws, "b.txt").write_text("2")
    _, second = ckpt.snapshot(1, root, "second")
    with pytest.raises(CheckpointError):
        ckpt.promote(second, root)  # the ref has already moved to `first`
    assert ckpt.verified_head() == first


def test_each_epoch_gets_its_own_workspace(ckpt):
    root = ckpt.verified_head()
    ws1 = ckpt.prepare_workspace(1, root)
    ws2 = ckpt.prepare_workspace(2, root)
    assert ws1 != ws2
    assert os.path.isdir(ws1) and os.path.isdir(ws2)
    Path(ws1, "README.md").write_text("stale epoch write")
    assert Path(ws2, "README.md").read_text() == "hello\n"


def test_export_of_an_empty_tree_writes_nothing(tmp_path):
    c = GitCheckpoint(str(tmp_path / "run"))
    root = c.init(None)
    _files_out = _files(c, root, tmp_path / "out")
    assert _files_out == []
