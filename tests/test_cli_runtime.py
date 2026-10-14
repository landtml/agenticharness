import json
import os
import subprocess
import sys

from conftest import make_spec


def urh(home, *args, env=None):
    return subprocess.run(
        [sys.executable, "-m", "urh.cli", "--home", str(home), *args],
        capture_output=True,
        text=True,
        env={**os.environ, **(env or {})},
        timeout=60,
    )


def test_trigger_commands_round_trip(tmp_path, hidden):
    spec = tmp_path / "spec.json"
    spec.write_text(json.dumps(make_spec(hidden).to_dict()))
    home = tmp_path / "home"
    assert urh(home, "trigger", "add-cron", "nightly", "0 3 * * *", str(spec)).returncode == 0
    r = urh(home, "trigger", "add-webhook", "push", str(spec), env={"URH_WEBHOOK_SECRET": "w" * 20})
    assert r.returncode == 0, r.stderr
    listed = [json.loads(line) for line in urh(home, "trigger", "list").stdout.splitlines()]
    assert {t["name"]: t["kind"] for t in listed} == {"nightly": "cron", "push": "webhook"}
    assert urh(home, "trigger", "disable", "nightly").returncode == 0
    assert urh(home, "trigger", "rm", "push").returncode == 0
    assert [json.loads(x)["enabled"] for x in urh(home, "trigger", "list").stdout.splitlines()] == [False]


def test_serve_refuses_to_start_without_a_token(tmp_path):
    r = urh(tmp_path / "home", "serve", env={"URH_API_TOKEN": ""})
    assert r.returncode != 0 and "URH_API_TOKEN" in r.stderr
