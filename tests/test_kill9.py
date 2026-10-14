"""The durability test the recipe asks for before any agent logic: a real SIGKILL mid-run.

A harness process is killed while a worker model call for step 2 is in flight.
A fresh process then takes the expired lease and finishes the run. Step 1 must
not be redone, its outward effect must not fire twice, and only step 2 (the
step in flight) is repeated: durability level D1.
"""

import json
import os
import signal
import subprocess
import sys
import time

from conftest import ADD_PY, MUL_PY, deliveries, make_spec

from urh.checkpoint import GitCheckpoint
from urh.journal import Journal

LEASE_TTL = 2.0


def _env(script_path: str, home: str) -> dict[str, str]:
    env = dict(os.environ)
    env.update(
        {
            "URH_PROVIDER": f"scripted:{script_path}",
            "URH_HOME": home,
            "URH_LEASE_TTL": str(LEASE_TTL),
            "URH_HEARTBEAT": "0.5",
            "URH_BACKOFF_S": "0",
        }
    )
    return env


def _urh(env, *args, **kw):
    return subprocess.run([sys.executable, "-m", "urh", *args], env=env, capture_output=True, text=True, **kw)


def test_sigkill_mid_step_resumes_without_redoing_verified_work(tmp_path, hidden):
    home = str(tmp_path / "home")
    marker = str(tmp_path / "hang.marker")
    script = {
        "steps": {
            "1": [
                [
                    {"write": "add.py", "content": ADD_PY},
                    {"effect": "outbox_file", "payload": {"msg": "add ready"}},
                ],
                [{"finish": "add written"}],
            ],
            "2": [
                [{"hang_once": marker}, {"write": "mul.py", "content": MUL_PY}],
                [{"finish": "mul written"}],
            ],
        }
    }
    script_path = str(tmp_path / "script.json")
    with open(script_path, "w") as f:
        json.dump(script, f)
    spec_path = str(tmp_path / "spec.json")
    with open(spec_path, "w") as f:
        json.dump(make_spec(hidden).to_dict(), f)
    env = _env(script_path, home)

    sub = _urh(env, "submit", spec_path, "--dedupe", "kill9")
    assert sub.returncode == 0, sub.stderr
    run_id = sub.stdout.strip()

    # First process: runs step 1 to a verified commit, then hangs inside step 2's first model call.
    proc = subprocess.Popen(
        [sys.executable, "-m", "urh", "run", run_id], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    deadline = time.time() + 60
    while not os.path.exists(marker):
        assert proc.poll() is None, proc.stderr.read().decode()
        assert time.time() < deadline, "harness never reached step 2"
        time.sleep(0.05)
    time.sleep(0.2)
    os.kill(proc.pid, signal.SIGKILL)
    proc.wait()
    assert proc.returncode == -signal.SIGKILL

    j = Journal(os.path.join(home, "journal.sqlite"))
    before = j.get_run(run_id)
    assert before.step_index == 1 and before.status == "running"
    assert [c["status"] for c in j.model_calls(run_id) if c["step_index"] == 1] == ["reserved"]
    assert len(deliveries(home)) == 1

    # A redelivered trigger maps to the same run instead of starting a second one.
    again = _urh(env, "submit", spec_path, "--dedupe", "kill9")
    assert again.stdout.strip() == run_id

    # Second process: a fresh lease can only be taken once the dead holder's lease expires.
    time.sleep(LEASE_TTL + 0.5)
    res = _urh(env, "run", run_id, timeout=120)
    assert res.returncode == 0, res.stderr
    assert res.stdout.strip() == "done"

    run = j.get_run(run_id)
    assert run.status == "done" and run.step_index == 2
    calls = j.model_calls(run_id)
    # Step 1: exactly the two scripted turns, never re-run.
    assert [(c["attempt"], c["call_index"]) for c in calls if c["step_index"] == 0] == [(1, 0), (1, 1)]
    # Step 2: the in-flight call was written off at its reservation, then the step re-ran once.
    step2 = [(c["attempt"], c["status"]) for c in calls if c["step_index"] == 1]
    assert step2 == [(1, "lost"), (2, "ok"), (2, "ok")]
    assert [a["status"] for a in j.attempts(run_id, 0)] == ["pass"]
    assert [a["status"] for a in j.attempts(run_id, 1)] == ["aborted", "pass"]
    # The outward effect from step 1 fired exactly once across both processes.
    assert len(deliveries(home)) == 1
    # Git holds one commit per verified step, on top of the seed.
    log = GitCheckpoint(os.path.join(home, "runs", run_id)).log()
    assert [m for _, m in log] == ["step 2: mul (attempt 2)", "step 1: add (attempt 1)", "urh: seed"]
    assert run.verified_commit == log[0][0]
    epochs = {e["epoch"] for e in j.events(run_id) if e["kind"] == "lease_acquired"}
    assert epochs == {1, 2}
