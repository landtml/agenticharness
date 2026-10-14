"""A real SIGKILL of `urh serve` while a webhook-started run is mid-step.

The webhook is redelivered after the kill (as senders do when they get no answer), then a
fresh server takes over. One delivery id must mean one run, the run must finish, and its
step-1 effect must fire once.
"""

import json
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

from conftest import ADD_PY, MUL_PY, deliveries, make_spec

from urh.journal import Journal
from urh.signing import sign

TOKEN = "k" * 24
SECRET = "w" * 24


def _port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _serve(env, port):
    return subprocess.Popen(
        [sys.executable, "-m", "urh", "serve", "--port", str(port), "--interval", "0.2"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def _post(port, path, body, headers, tries=100):
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=body, headers=headers, method="POST")
    for _ in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status, json.load(r)
        except urllib.error.URLError:
            time.sleep(0.1)  # server still starting
    raise AssertionError("server never answered")


def test_sigkill_serve_mid_run_then_redelivered_hook_makes_no_second_run(tmp_path, hidden):
    home, marker = str(tmp_path / "home"), str(tmp_path / "hang.marker")
    script = {
        "steps": {
            "1": [
                [
                    {"write": "add.py", "content": ADD_PY},
                    {"effect": "outbox_file", "payload": {"msg": "add"}},
                ],
                [{"finish": "add"}],
            ],
            "2": [[{"hang_once": marker}, {"write": "mul.py", "content": MUL_PY}], [{"finish": "mul"}]],
        }
    }
    (tmp_path / "script.json").write_text(json.dumps(script))
    (tmp_path / "spec.json").write_text(json.dumps(make_spec(hidden).to_dict()))
    env = {
        **os.environ,
        "URH_PROVIDER": f"scripted:{tmp_path / 'script.json'}",
        "URH_HOME": home,
        "URH_LEASE_TTL": "2",
        "URH_HEARTBEAT": "0.5",
        "URH_BACKOFF_S": "0",
        "URH_API_TOKEN": TOKEN,
        "URH_WEBHOOK_SECRET": SECRET,
    }
    add = subprocess.run(
        [sys.executable, "-m", "urh", "trigger", "add-webhook", "push", str(tmp_path / "spec.json")],
        env=env,
        capture_output=True,
        text=True,
    )
    assert add.returncode == 0, add.stderr

    body = b'{"ref": "refs/heads/main"}'
    headers = {"X-URH-Signature": sign(SECRET, body), "X-URH-Delivery": "delivery-1"}
    port = _port()
    first = _serve(env, port)
    try:
        status, hook = _post(port, "/hooks/push", body, headers)
        assert status == 201
        deadline = time.time() + 60
        while not os.path.exists(marker):
            assert first.poll() is None, first.stderr.read().decode()
            assert time.time() < deadline, "never reached step 2"
            time.sleep(0.05)
    finally:
        os.kill(first.pid, signal.SIGKILL)
        first.wait()

    port = _port()
    second = _serve(env, port)
    try:
        status, again = _post(port, "/hooks/push", body, headers)  # the sender redelivers
        assert (status, again["run_id"], again["created"]) == (200, hook["run_id"], False)
        auth = {"Authorization": f"Bearer {TOKEN}"}
        deadline = time.time() + 60
        while True:
            req = urllib.request.Request(f"http://127.0.0.1:{port}/v1/runs/{hook['run_id']}", headers=auth)
            with urllib.request.urlopen(req, timeout=5) as r:
                run = json.load(r)
            if run["status"] == "done":
                break
            assert time.time() < deadline, run
            time.sleep(0.2)
    finally:
        second.send_signal(signal.SIGTERM)
        assert second.wait(timeout=30) == 0  # clean shutdown, not killed by the signal

    j = Journal(os.path.join(home, "journal.sqlite"))
    assert len(j.list_runs()) == 1
    assert len(deliveries(home)) == 1
    step1 = [a for a in j.attempts(hook["run_id"]) if a["step_index"] == 0]
    assert [a["status"] for a in step1] == ["pass"]  # verified work was not redone
