import json

import pytest
from conftest import ADD_PY, MUL_PY, deliveries, good_script, make_spec

from urh.checkpoint import GitCheckpoint
from urh.journal import LeaseLost


def test_happy_path_commits_each_step_and_fires_effect_once(harness_factory, hidden, tmp_path):
    h = harness_factory(good_script())
    rid = h.submit(make_spec(hidden))
    assert h.run(rid) == "done"
    run = h.journal.get_run(rid)
    assert run.step_index == 2
    log = GitCheckpoint(str(tmp_path / "home" / "runs" / rid)).log()
    assert [m for _, m in log] == ["step 2: mul (attempt 1)", "step 1: add (attempt 1)", "urh: seed"]
    assert len(deliveries(tmp_path / "home")) == 1
    assert [e["status"] for e in h.journal.effects(rid)] == ["done"]
    # Every model call is logged with its cost, and the reservation is settled.
    calls = h.journal.model_calls(rid)
    assert calls and all(c["status"] == "ok" and c["model"] == "claude-haiku-5-5" for c in calls)
    assert run.reserved_usd == 0 and run.spent_usd > 0


def test_worker_never_sees_hidden_tests_or_real_paths(harness_factory, hidden, tmp_path):
    script = good_script()
    script["steps"]["1"][0].insert(0, {"bash": "pwd; ls -a"})
    h = harness_factory(script)
    rid = h.submit(make_spec(hidden))
    h.run(rid)
    blobs = h.blobs
    for call in h.journal.model_calls(rid):
        req = blobs.get_bytes(call["request_blob"]).decode()
        assert str(tmp_path) not in req
        assert "test_add" not in req


def test_failed_check_triggers_repair_that_must_differ(harness_factory, hidden):
    script = good_script(
        **{
            "1": [
                [{"write": "add.py", "content": "def add(a, b):\n    return a - b\n"}],
                [{"finish": "oops"}],
            ],
            "1@2": [[{"write": "add.py", "content": ADD_PY}], [{"finish": "fixed"}]],
        }
    )
    h = harness_factory(script)
    rid = h.submit(make_spec(hidden))
    assert h.run(rid) == "done"
    attempts = h.journal.attempts(rid, 0)
    assert [a["status"] for a in attempts] == ["fail", "pass"]
    assert "test_add.py::test_add" in " ".join(attempts[0]["verdict"]["failures"])


def test_failed_attempt_effects_are_discarded_not_fired(harness_factory, hidden, tmp_path):
    script = good_script(
        **{
            "1": [
                [
                    {"write": "add.py", "content": "def add(a, b):\n    return 0\n"},
                    {"effect": "outbox_file", "payload": {"msg": "premature"}},
                ],
                [{"finish": "x"}],
            ],
            "1@2": [[{"write": "add.py", "content": ADD_PY}], [{"finish": "fixed"}]],
        }
    )
    h = harness_factory(script)
    rid = h.submit(make_spec(hidden))
    assert h.run(rid) == "done"
    assert deliveries(tmp_path / "home") == []


def test_identical_repairs_count_as_failures_then_escalate_then_park(harness_factory, hidden):
    bad = [[{"write": "add.py", "content": "def add(a, b):\n    return 0\n"}], [{"finish": "x"}]]
    h = harness_factory(good_script(**{"1": bad}))
    rid = h.submit(make_spec(hidden))
    assert h.run(rid) == "parked"
    assert h.journal.parks(rid)[0]["reason"] == "repairs_exhausted"
    attempts = h.journal.attempts(rid, 0)
    assert [a["status"] for a in attempts] == ["fail"] * 4  # 1 + max_repairs(2) + 1 escalation
    assert "no progress" in attempts[1]["verdict"]["summary"]
    roles = {(c["attempt"], c["role"], c["model"]) for c in h.journal.model_calls(rid)}
    assert (4, "escalation", "claude-opus-5-5") in roles


def test_escalation_rescues_step_without_a_person(harness_factory, hidden):
    script = good_script(
        **{
            "1": [[{"write": "add.py", "content": "def add(a, b):\n    return 0\n"}], [{"finish": "x"}]],
            "1@2": [[{"write": "add.py", "content": "def add(a, b):\n    return 1\n"}], [{"finish": "x"}]],
            "1@3": [[{"write": "add.py", "content": ADD_PY}], [{"finish": "ok"}]],
        }
    )
    h = harness_factory(script)
    rid = h.submit(make_spec(hidden, max_repairs=1))
    assert h.run(rid) == "done"
    assert h.journal.parks(rid) == []
    assert [a["status"] for a in h.journal.attempts(rid, 0)] == ["fail", "fail", "pass"]


def test_park_answer_is_claimed_once_and_reaches_the_worker(harness_factory, hidden):
    bad = [[{"write": "add.py", "content": "def add(a, b):\n    return 0\n"}], [{"finish": "x"}]]
    h = harness_factory(good_script(**{"1": bad}), escalate=False)
    rid = h.submit(make_spec(hidden, max_repairs=0))
    assert h.run(rid) == "parked"
    park = h.journal.parks(rid, status="open")[0]
    h.gateway.provider.script["steps"]["1@2"] = [[{"write": "add.py", "content": ADD_PY}], [{"finish": "ok"}]]
    h.journal.answer_park(park["id"], "add must return the sum")
    spec = make_spec(hidden, max_repairs=3)
    with h.journal.tx() as c:
        c.execute("UPDATE runs SET spec_json=? WHERE id=?", (json.dumps(spec.to_dict()), rid))
    assert h.run(rid) == "done"
    assert h.journal.parks(rid)[0]["status"] == "claimed"
    first = [c for c in h.journal.model_calls(rid) if c["attempt"] == 2 and c["call_index"] == 0][0]
    assert "add must return the sum" in h.blobs.get_bytes(first["request_blob"]).decode()


def test_budget_exhaustion_parks_and_top_up_resumes(harness_factory, hidden):
    h = harness_factory(good_script())
    rid = h.submit(make_spec(hidden), budget_usd=0.0001)
    assert h.run(rid) == "parked"
    park = h.journal.parks(rid, status="open")[0]
    assert park["reason"] == "budget"
    assert h.journal.get_run(rid).denials >= 1
    h.journal.add_budget(rid, 1.0)
    h.journal.answer_park(park["id"], "topped up")
    assert h.run(rid) == "done"


def test_provider_outage_parks_run(harness_factory, hidden):
    script = good_script()
    script["fail_calls"] = 100
    h = harness_factory(script)
    rid = h.submit(make_spec(hidden))
    assert h.run(rid) == "parked"
    assert h.journal.parks(rid)[0]["reason"] == "outage"
    assert h.journal.get_run(rid).reserved_usd == 0


def test_irreversible_effect_waits_for_approval(harness_factory, hidden, tmp_path):
    spec = make_spec(hidden)
    spec.steps[1].effects = [{"kind": "outbox_file", "payload": {"deploy": "prod"}}]
    spec.steps[1].irreversible = True
    h = harness_factory(good_script())
    rid = h.submit(spec)
    assert h.run(rid) == "parked"
    park = h.journal.parks(rid, status="open")[0]
    assert park["reason"] == "effect"
    assert len(deliveries(tmp_path / "home")) == 1  # only step 1's reversible effect
    h.journal.answer_park(park["id"], "approve")
    assert h.run(rid) == "done"
    assert len(deliveries(tmp_path / "home")) == 2


def test_redelivered_trigger_maps_to_same_run(harness_factory, hidden):
    h = harness_factory(good_script())
    a = h.submit(make_spec(hidden), dedupe_key="issue-7")
    b = h.submit(make_spec(hidden), dedupe_key="issue-7")
    assert a == b and len(h.journal.list_runs()) == 1


def test_llm_manager_plans_novel_task_with_opus(harness_factory, hidden):
    script = good_script()
    script["plan"] = [
        {"title": "add", "instructions": "Write add.py", "files": ["add.py"], "checks": ["add"]},
        {"title": "mul", "instructions": "Write mul.py", "files": ["mul.py"], "checks": []},
        {"done": True},
    ]
    h = harness_factory(script)
    rid = h.submit(make_spec(hidden, steps=None))
    assert h.run(rid) == "done"
    roles = {(c["role"], c["model"]) for c in h.journal.model_calls(rid)}
    assert ("manager", "claude-opus-5-5") in roles and ("worker", "claude-haiku-5-5") in roles


def test_stale_lease_holder_cannot_advance_run(harness_factory, hidden):
    h = harness_factory(good_script())
    rid = h.submit(make_spec(hidden))
    stale = h.journal.acquire_lease(rid, "old-process", ttl=0.0)
    assert stale is not None
    assert h.run(rid) == "done"  # takes over the expired lease with a new epoch
    with pytest.raises(LeaseLost):
        h.journal.complete_step(rid, stale, 2, "f" * 40)


def test_mul_content_constant_is_valid():
    ns: dict = {}
    exec(MUL_PY, ns)
    assert ns["mul"](3, 4) == 12


def test_budget_policy_tops_up_instead_of_parking(harness_factory, hidden):
    h = harness_factory(good_script(), auto_topup_usd=0.5, max_auto_topups=1)
    rid = h.submit(make_spec(hidden), budget_usd=0.0001)
    assert h.run(rid) == "done"
    assert h.journal.parks(rid) == []
    assert [e["kind"] for e in h.journal.events(rid)].count("auto_topup") == 1


def test_outage_park_wakes_itself_after_cooldown(harness_factory, hidden):
    script = good_script()
    script["fail_calls"] = 3  # retries=2 means 3 failed tries, then the provider recovers
    h = harness_factory(script, outage_wake_s=0.0)
    rid = h.submit(make_spec(hidden))
    assert h.run(rid) == "parked"
    assert h.journal.parks(rid)[0]["reason"] == "outage"
    assert h.run_pending() == {}  # the breaker is still open: waking now would just park again
    h.gateway.breaker.cooldown_s = 0.0
    assert h.run_pending() == {rid: "done"}
    assert h.journal.parks(rid)[0]["answer"].startswith("auto:")


def test_judge_decides_step_no_script_covers(harness_factory, hidden):
    script = good_script()
    script["judge"] = [
        {"verdict": "fail", "reasons": ["mul is missing a docstring"]},
        {"verdict": "pass", "reasons": []},
    ]
    script["steps"]["2@2"] = [
        [{"write": "mul.py", "content": '"""Multiply."""\n' + MUL_PY}],
        [{"finish": "ok"}],
    ]
    spec = make_spec(hidden)
    spec.steps[1].checks = ["nonexistent"]  # no script applies
    h = harness_factory(script)
    rid = h.submit(spec)
    assert h.run(rid) == "done"
    statuses = [a["status"] for a in h.journal.attempts(rid, 1)]
    assert statuses == ["fail", "pass"]
    judge_calls = [c for c in h.journal.model_calls(rid) if c["role"] == "judge"]
    assert len(judge_calls) == 2
    req = h.blobs.get_bytes(judge_calls[0]["request_blob"]).decode()
    assert "mul written" not in req  # blind to the worker's own summary
