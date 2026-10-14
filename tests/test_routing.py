import pytest
from conftest import MUL_PY, fast_config, make_spec
from test_planner import BAD_MUL, ONE, PlannerProvider, mplan, pstep, steps_script

from urh.gateway import DEFAULT_MODELS
from urh.orchestrator import Harness
from urh.planner import PLANNER_SYSTEM
from urh.routing import Route, cascade, load_routing, resolve_routes, route_for

CHEAP = {"planner": "claude-haiku-5-5", "manager": "claude-opus-5-5"}
LO, HI = CHEAP["planner"], CHEAP["manager"]


class RecordingPlanner(PlannerProvider):
    """Also records which model and effort each planner call used."""

    def __init__(self, script, plans):
        super().__init__(script, plans)
        self.planner_calls: list[tuple[str, str | None]] = []

    def complete(self, request):
        system = "".join(b.get("text", "") for b in request.get("system", []))
        if system.startswith(PLANNER_SYSTEM[:40]):
            self.planner_calls.append((request["model"], request.get("effort")))
        return super().complete(request)


@pytest.fixture
def make(tmp_path):
    def _make(script, plans, **cfg):
        provider = RecordingPlanner(script, plans)
        return Harness(str(tmp_path / "home"), provider, config=fast_config(**cfg)), provider

    return _make


def test_default_routes_keep_todays_behaviour():
    r = resolve_routes(None, "medium", "high")
    assert r["plan"] == {"roles": ["planner", "manager"], "effort": "medium"}
    assert r["replan"] == {"roles": ["manager"], "effort": "high"}


def test_route_overrides_are_validated():
    assert resolve_routes({"plan": {"effort": "low"}})["plan"]["roles"] == ["planner", "manager"]
    assert resolve_routes({"replan": {"role": "planner"}})["replan"]["roles"] == ["planner"]
    with pytest.raises(ValueError, match="unknown route site"):
        resolve_routes({"attempt": {"roles": ["worker"]}})
    with pytest.raises(ValueError, match="effort"):
        resolve_routes({"plan": {"effort": "max"}})
    with pytest.raises(ValueError, match="at least one role"):
        resolve_routes({"plan": {"roles": []}})


def test_load_routing_presets_and_json():
    assert load_routing(None) == ({}, {})
    routes, models = load_routing("cheap-plan")
    assert routes == {} and models == {"planner": "claude-haiku-5-5"}
    assert load_routing('{"plan": {"effort": "low"}}') == ({"plan": {"effort": "low"}}, {})
    routes, models = load_routing('{"preset": "cheap-plan", "routes": {"expand": {"roles": ["manager"]}}}')
    assert routes == {"expand": {"roles": ["manager"]}} and models["planner"] == "claude-haiku-5-5"
    with pytest.raises(ValueError):
        load_routing("no-such-preset")


def test_cascade_skips_roles_that_repeat_a_model_or_are_not_pinned():
    pins = {"models": {"planner": "a", "manager": "a", "worker": "b"}}
    assert cascade(pins, Route(("planner", "manager", "worker", "ghost"))) == ["planner", "worker"]


def test_route_for_falls_back_for_runs_pinned_before_routing():
    fallback = Route(("manager",), "high")
    assert route_for({}, "replan", fallback) == fallback
    assert route_for({"routes": {"plan": {"roles": ["x"], "effort": None}}}, "plan", fallback).roles == ("x",)


def test_routes_are_pinned_on_the_run(make, hidden):
    h, _ = make(steps_script(), [ONE], routes={"plan": {"effort": "low"}})
    rid = h.submit(make_spec(hidden, steps=None))
    pins = h.journal.get_run(rid).pins
    assert pins["routes"]["plan"]["effort"] == "low"
    assert pins["models"]["planner"] == DEFAULT_MODELS["planner"]


def test_cheap_planner_plans_and_strong_model_is_not_called(make, hidden):
    h, p = make(steps_script(), [ONE], models=CHEAP)
    rid = h.submit(make_spec(hidden, steps=None))
    assert h.run(rid) == "done"
    assert p.planner_calls == [(LO, "medium")]
    assert [c["role"] for c in h.journal.model_calls(rid) if c["attempt"] == 0] == ["planner"]


def test_rejected_cheap_plan_falls_back_to_the_strong_model(make, hidden):
    bad = mplan([pstep("add", spec_checks=["nope"])])
    h, p = make(steps_script(), [bad, "not json", ONE], models=CHEAP)
    rid = h.submit(make_spec(hidden, steps=None))
    assert h.run(rid) == "done"
    assert [m for m, _ in p.planner_calls] == [LO, LO, HI]
    (fb,) = [e for e in h.journal.events(rid) if e["kind"] == "plan_fallback"]
    assert (fb["from_role"], fb["to_role"], fb["why"]) == ("planner", "manager", "plan")
    (plan_event,) = [e for e in h.journal.events(rid) if e["kind"] == "plan"]
    assert plan_event["role"] == "manager"


def test_replans_go_to_the_strong_model_at_replan_effort(make, hidden):
    fixed = mplan(
        [
            pstep("add", spec_checks=["add"]),
            pstep("mul", instructions="Write mul.py (v2): multiply", spec_checks=["add", "mul"]),
        ]
    )
    script = steps_script(**{"2": [[{"write": "mul.py", "content": BAD_MUL}], [{"finish": "mul"}]]})
    script["by_marker"] = {"(v2)": [[{"write": "mul.py", "content": MUL_PY}], [{"finish": "mul v2"}]]}
    h, p = make(script, [ONE, fixed], models=CHEAP)
    rid = h.submit(make_spec(hidden, steps=None))
    assert h.run(rid) == "done"
    assert p.planner_calls == [(LO, "medium"), (HI, "high")]


def test_the_plan_call_limit_holds_across_the_cascade(make, hidden):
    h, p = make(steps_script(), ["x", "x", "x", "x"], models=CHEAP)
    h.planner.max_plan_calls = 3
    rid = h.submit(make_spec(hidden, steps=None))
    assert h.run(rid) == "parked"
    assert [m for m, _ in p.planner_calls] == [LO, LO, HI]


@pytest.mark.parametrize(
    "check,bad",
    [
        ("python3 -m pytest -q test_slug.py", True),
        ("pytest", True),
        ("python3 -m unittest discover", True),
        ("python3 tests/test_slug.py", True),
        ("python3 -c \"from slug import slugify; assert slugify('A b') == 'a-b'\"", False),
        ("test -f test_slug.py", False),
        ("python3 -m todo --file /tmp/x list", False),
    ],
)
def test_plan_checks_may_not_run_tests_the_workers_write(check, bad):
    """Cheap planners wrote pytest plan checks on the live bench; the validator now catches it for free."""
    from urh.planner import plan_errors

    plan = mplan([pstep("add", plan_checks=[check], spec_checks=["add"])])
    assert any("run tests the workers write" in e for e in plan_errors(plan, ["add"])) is bad
