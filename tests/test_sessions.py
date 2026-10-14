import json

import pytest
from conftest import ADD_PY, MUL_PY

from urh.sessions import Sessions


def template(hidden):
    return {
        "constraints": ["Standard library only"],
        "gate": {"hidden_dir": hidden, "checks": [], "protected": ["_hidden/"]},
    }


def script():
    return {
        "by_goal": {
            "Write add.py": {
                "plan": [{"title": "add", "instructions": "Write add.py", "files": ["add.py"]}],
                "steps": {"1": [[{"write": "add.py", "content": ADD_PY}], [{"finish": "add"}]]},
            },
            "Now add mul.py": {
                "plan": [{"title": "mul", "instructions": "Write mul.py", "files": ["mul.py"]}],
                "steps": {"1": [[{"write": "mul.py", "content": MUL_PY}], [{"finish": "mul"}]]},
            },
        }
    }


@pytest.fixture
def sess(harness_factory):
    h = harness_factory(script(), manager="stepwise")  # the script drives the stepwise manager's plan
    return h, Sessions(h)


def test_follow_up_builds_on_the_previous_verified_tree(sess, hidden):
    h, s = sess
    sid = s.create("arith", template(hidden), budget_usd=1.0)
    assert s.send(sid, "Write add.py with add(a, b)") == 1
    assert s.send(sid, "Now add mul.py with mul(a, b)") == 2
    view = s.view(sid)
    assert [m["status"] for m in view["messages"]] == ["queued", "waiting"]  # message 2 waits its turn
    first = view["messages"][0]["run_id"]
    assert h.run(first) == "done"
    (second,) = s.advance()
    assert h.run(second) == "done"
    files = s.files(sid)
    assert set(files) >= {"add.py", "mul.py"}  # mul was written on top of verified add
    inputs = h.journal.get_run(second).spec["inputs"]
    assert inputs["earlier"] == [{"seq": 1, "message": "Write add.py with add(a, b)", "outcome": "done"}]
    manager = [c for c in h.journal.model_calls(second) if c["role"] == "manager"][0]
    assert (
        "Write add.py with add(a, b)" in h.blobs.get_bytes(manager["request_blob"]).decode()
    )  # planner sees history


def test_advance_is_idempotent_and_crash_safe(sess, hidden, monkeypatch):
    h, s = sess
    sid = s.create("arith", template(hidden))
    monkeypatch.setattr(
        h.journal, "bind_session_message", lambda *a: (_ for _ in ()).throw(SystemExit("kill"))
    )
    with pytest.raises(SystemExit):
        s.send(sid, "Write add.py with add(a, b)")
    monkeypatch.undo()
    assert len(h.journal.list_runs()) == 1  # the run exists; the message is not bound yet
    again = s.advance()
    assert again == [h.journal.list_runs()[0].id] and len(h.journal.list_runs()) == 1
    assert s.advance() == []


def test_parked_predecessor_holds_the_session(sess, hidden):
    h, s = sess
    h.config.use_judge = False
    h.config.escalate = False
    sid = s.create("arith", template(hidden))
    s.send(sid, "Write add.py with add(a, b)")  # no script check covers it and no judge: parks
    s.send(sid, "Now add mul.py with mul(a, b)")
    first = s.view(sid)["messages"][0]["run_id"]
    assert h.run(first) == "parked"
    assert s.advance() == []
    assert s.view(sid)["messages"][1]["status"] == "waiting"


def test_template_cannot_fix_steps(sess, hidden):
    _, s = sess
    with pytest.raises(ValueError):
        s.create("x", {**template(hidden), "steps": [{"title": "a", "instructions": "b"}]})
    assert json.dumps(template(hidden))  # sanity: template is plain data
