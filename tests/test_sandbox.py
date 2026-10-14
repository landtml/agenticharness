"""The jail: a command sees its own folder at /work and nothing else of the host's to read or write."""

import os

import pytest

from urh import sandbox
from urh.worker import Workspace

pytestmark = pytest.mark.skipif(not sandbox.jail_available(), reason="no user/mount namespaces here")


def test_worker_cannot_leave_its_workspace(tmp_path):
    secret_dir = tmp_path / "harness-home"
    secret_dir.mkdir()
    (secret_dir / "journal.sqlite").write_text("secret")
    sandbox.hide(str(secret_dir))
    ws = tmp_path / "ws"
    ws.mkdir()
    out = Workspace(str(ws)).bash(
        "cd /; ls /home; touch /home/x || echo BLOCKED-home; touch /usr/x || echo BLOCKED-usr; "
        f"cat {secret_dir}/journal.sqlite || echo HIDDEN; cat {os.path.abspath(__file__)} || echo NO-REPO"
    )
    assert "BLOCKED-home" in out and "BLOCKED-usr" in out
    assert "HIDDEN" in out and "secret" not in out.splitlines()
    assert "NO-REPO" in out
    assert not os.path.exists("/home/x")


def test_workspace_is_writable_and_shared_with_the_host(tmp_path):
    r = sandbox.run("pwd; echo made > out.txt; echo $HOME", cwd=str(tmp_path))
    assert r.returncode == 0, r.stderr
    assert r.stdout.split() == ["/work", "/work"]
    assert (tmp_path / "out.txt").read_text() == "made\n"


def test_no_host_processes_and_no_network(tmp_path):
    r = sandbox.run("ls /proc | grep -c '^[0-9]'; cat /proc/1/cmdline | tr '\\0' ' '", cwd=str(tmp_path))
    assert int(r.stdout.split()[0]) < 10  # only the jail's own processes
    r = sandbox.run(
        "python -c \"import socket; socket.create_connection(('1.1.1.1', 53), 2)\"", cwd=str(tmp_path)
    )
    assert r.returncode != 0


def test_python_and_pytest_still_work(tmp_path):
    (tmp_path / "test_x.py").write_text("def test_ok():\n    assert 1 + 1 == 2\n")
    r = sandbox.run("python -m pytest -q -p no:cacheprovider", cwd=str(tmp_path), timeout=120)
    assert r.returncode == 0, r.stdout + r.stderr


def test_require_refuses_without_a_jail(tmp_path, monkeypatch):
    monkeypatch.setattr(sandbox, "jail_available", lambda: False)
    monkeypatch.setenv("URH_SANDBOX", "require")
    r = sandbox.run("echo hi", cwd=str(tmp_path))
    assert r.returncode == 126 and "sandbox required" in r.stderr
