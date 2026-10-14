import json
import subprocess
import sys


def run(tmp_path, *args):
    return subprocess.run(
        [sys.executable, "-m", "todo", "--file", str(tmp_path / "t.json"), *args],
        capture_output=True,
        text=True,
    )


def test_flow(tmp_path):
    assert run(tmp_path, "list").stdout.strip() == ""
    assert run(tmp_path, "add", "buy milk").stdout.strip() == "1"
    assert run(tmp_path, "add", "call bob").stdout.strip() == "2"
    assert run(tmp_path, "done", "1").returncode == 0
    assert run(tmp_path, "list").stdout.splitlines() == ["1 [x] buy milk", "2 [ ] call bob"]
    assert run(tmp_path, "list", "--pending").stdout.splitlines() == ["2 [ ] call bob"]


def test_ids_not_reused(tmp_path):
    run(tmp_path, "add", "a")
    run(tmp_path, "add", "b")
    assert run(tmp_path, "remove", "2").returncode == 0
    assert run(tmp_path, "add", "c").stdout.strip() == "3"


def test_unknown_id(tmp_path):
    r = run(tmp_path, "done", "9")
    assert r.returncode == 2 and r.stderr.strip()
    r = run(tmp_path, "remove", "9")
    assert r.returncode == 2


def test_file_is_json(tmp_path):
    run(tmp_path, "add", "x")
    data = json.loads((tmp_path / "t.json").read_text())
    assert "x" in json.dumps(data)


def test_modules_exist():
    import todo.core  # noqa: F401
