from conftest import good_script, make_spec

from urh import stats


def test_auto_answered_parks_are_not_human_touches(harness_factory, hidden):
    script = good_script()
    script["fail_calls"] = 3
    h = harness_factory(script, outage_wake_s=0.0)
    ok = h.submit(make_spec(hidden))
    assert h.run(ok) == "parked"
    h.gateway.breaker.cooldown_s = 0.0
    assert h.run_pending() == {ok: "done"}

    s = stats.compute(h.journal)
    assert s["runs"] == 1 and s["by_status"] == {"done": 1}
    assert s["human_touches"] == 0 and s["park_rate"] == 0.0
    assert s["auto_resolved_parks"] == 1 and s["headless_done"] == 1
    assert s["cost_per_done_usd"] > 0 and s["calls_per_done"] >= 4


def test_open_and_person_answered_parks_count_against_the_run(harness_factory, hidden):
    h = harness_factory(good_script(), escalate=False, use_judge=False)
    spec = make_spec(hidden)
    spec.steps[1].checks = ["nonexistent"]  # unsure with no judge parks for a person
    rid = h.submit(spec)
    assert h.run(rid) == "parked"
    s = stats.compute(h.journal)
    assert s["human_touches"] == 1 and s["park_rate"] == 1.0 and s["headless_done"] == 0
