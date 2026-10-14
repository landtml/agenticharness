import json
import sys

import pytest
from conftest import ADD_PY, MUL_PY, fast_config, make_spec

from urh.orchestrator import Harness, escalate_effort
from urh.planner import PLANNER_SYSTEM, Milestone, Plan, PlanStep, locked_prefix_errors, plan_errors
from urh.testing import ScriptedProvider

PY = sys.executable
BAD_MUL = "def mul(a, b):\n    return a + b\n"


def pstep(id, milestone="m1", **kw):
    d = dict(
        id=id,
        milestone=milestone,
        title=id,
        instructions=f"Write {id}.py",
        expected_output=f"{id}.py with {id}(a, b)",
        files=[f"{id}.py"],
        plan_checks=[f'{PY} -c "from {id} import {id}"'],
        spec_checks=[],
        effort="low",
    )
    d.update(kw)
    return PlanStep(**d)


def mplan(steps, milestones=("m1",)):
    return Plan(milestones=[Milestone(id=m, title=m, outline=f"{m} done") for m in milestones], steps=steps)


ONE = mplan([pstep("add", spec_checks=["add"]), pstep("mul", spec_checks=["add", "mul"])])


class PlannerProvider(ScriptedProvider):
    """Serves queued plans to planner calls and scripted turns to workers.

    ``by_marker`` picks a worker's turns by a string in its step message, so a replanned step
    can behave differently from the step it replaced.
    """

    def __init__(self, script, plans):
        super().__init__(script)
        self.plans = list(plans)
        self.planner_prompts: list[str] = []
        self.worker_efforts: list[str] = []

    def complete(self, request):
        system = "".join(b.get("text", "") for b in request.get("system", []))
        if system.startswith(PLANNER_SYSTEM[:40]):
            self.calls += 1
            self.planner_prompts.append(request["messages"][0]["content"])
            item = self.plans.pop(0)
            text = item if isinstance(item, str) else item.model_dump_json()
            from urh.gateway import ProviderResponse

            return ProviderResponse(
                [{"type": "text", "text": text}],
                "end_turn",
                {"input_tokens": 500, "output_tokens": 300},
                request["model"],
            )
        first = request["messages"][0]["content"]
        if len(request["messages"]) == 1:
            self.worker_efforts.append(request["effort"])
        for marker, turns in self.script.get("by_marker", {}).items():
            if marker in first:
                turn = sum(1 for m in request["messages"] if m["role"] == "assistant")
                return self._turn(request, turns, turn)
        return super().complete(request)

    def _turn(self, request, turns, turn):
        from urh.gateway import ProviderResponse

        if turn >= len(turns):
            return ProviderResponse([{"type": "text", "text": "done"}], "end_turn", {}, request["model"])
        content = []
        for n, a in enumerate(turns[turn]):
            tid = f"toolu_m{self.calls}_{n}"
            if "write" in a:
                content.append(
                    {
                        "type": "tool_use",
                        "id": tid,
                        "name": "write_file",
                        "input": {"path": a["write"], "content": a["content"]},
                    }
                )
            elif "finish" in a:
                content.append(
                    {"type": "tool_use", "id": tid, "name": "finish", "input": {"summary": a["finish"]}}
                )
        return ProviderResponse(content, "tool_use", {}, request["model"])


def steps_script(**over):
    steps = {
        "1": [[{"write": "add.py", "content": ADD_PY}], [{"finish": "add"}]],
        "2": [[{"write": "mul.py", "content": MUL_PY}], [{"finish": "mul"}]],
    }
    steps.update(over)
    return {"steps": steps}


@pytest.fixture
def make(tmp_path):
    def _make(script, plans, **cfg):
        provider = PlannerProvider(script, plans)
        return Harness(str(tmp_path / "home"), provider, config=fast_config(**cfg)), provider

    return _make


def test_one_planner_call_drives_every_step(make, hidden):
    h, p = make(steps_script(), [ONE])
    rid = h.submit(make_spec(hidden, steps=None))
    assert h.run(rid) == "done"
    roles = [c["role"] for c in h.journal.model_calls(rid)]
    assert roles.count("manager") == 1
    assert [e["why"] for e in h.journal.events(rid) if e["kind"] == "plan"] == ["plan"]
    # The worker sees its expected output and the gate's plan checks; planner prompts mark the goal untrusted.
    assert (
        "<untrusted>" in p.planner_prompts[0]
        and "TASK CHECKS (spec_checks): add, mul" in p.planner_prompts[0]
    )
    assert p.worker_efforts == ["low", "low"]


def test_milestones_expand_one_at_a_time_from_verified_facts(make, hidden):
    first = mplan([pstep("add", spec_checks=["add"])], milestones=("m1", "m2"))
    second = mplan(
        [pstep("add", spec_checks=["add"]), pstep("mul", "m2", spec_checks=["add", "mul"])],
        milestones=("m1", "m2"),
    )
    h, p = make(steps_script(), [first, second])
    rid = h.submit(make_spec(hidden, steps=None))
    assert h.run(rid) == "done"
    assert [e["why"] for e in h.journal.events(rid) if e["kind"] == "plan"] == ["plan", "expand"]
    assert "add.py" in p.planner_prompts[1] and "Expand milestone 'm2'" in p.planner_prompts[1]


def test_rejected_plan_is_retried_once_then_parks(make, hidden):
    no_check = mplan([pstep("add", plan_checks=[]), pstep("mul", spec_checks=["add", "mul"])])
    h, p = make(steps_script(), [no_check, "not json", ONE])
    rid = h.submit(make_spec(hidden, steps=None))
    assert h.run(rid) == "parked"
    assert "has no check" in p.planner_prompts[1]
    (park,) = h.journal.parks(rid, status="open")
    assert park["reason"] == "plan"


def test_retry_with_errors_recovers(make, hidden):
    bad = mplan([pstep("add", spec_checks=["nope"])])
    h, p = make(steps_script(), [bad, ONE])
    rid = h.submit(make_spec(hidden, steps=None))
    assert h.run(rid) == "done"
    assert "unknown spec checks ['nope']" in p.planner_prompts[1]


def test_exhausted_repairs_replan_instead_of_parking(make, hidden):
    fixed = mplan(
        [
            pstep("add", spec_checks=["add"]),
            pstep("mul", instructions="Write mul.py (v2): multiply", spec_checks=["add", "mul"]),
        ]
    )
    script = steps_script(**{"2": [[{"write": "mul.py", "content": BAD_MUL}], [{"finish": "mul"}]]})
    script["by_marker"] = {"(v2)": [[{"write": "mul.py", "content": MUL_PY}], [{"finish": "mul v2"}]]}
    h, p = make(script, [ONE, fixed])
    rid = h.submit(make_spec(hidden, steps=None))
    assert h.run(rid) == "done"
    statuses = [a["status"] for a in h.journal.attempts(rid, 1)]
    assert statuses[-1] == "pass" and "superseded" in statuses
    assert [e["why"] for e in h.journal.events(rid) if e["kind"] == "plan"] == ["plan", "replan"]
    assert "kept failing" in p.planner_prompts[1]
    # Repairs climb the effort ladder; an unchanged repair counts as a failure; one escalation try runs
    # before the replan, and the replanned step starts again at its own effort.
    efforts = p.worker_efforts
    assert efforts[:3] == ["low", "low", "medium"] and efforts[-1] == "low"
    assert any(e["kind"] == "escalated" for e in h.journal.events(rid))


def test_replan_that_repeats_the_failed_step_is_rejected(make, hidden):
    script = steps_script(**{"2": [[{"write": "mul.py", "content": BAD_MUL}], [{"finish": "mul"}]]})
    h, p = make(script, [ONE, ONE, ONE])
    rid = h.submit(make_spec(hidden, steps=None))
    assert h.run(rid) == "parked"
    assert "must change" in p.planner_prompts[2]
    assert any(e["kind"] == "replan_failed" for e in h.journal.events(rid))


def test_resume_reads_the_plan_from_the_journal(make, hidden, tmp_path):
    h, p = make(steps_script(), [ONE])
    rid = h.submit(make_spec(hidden, steps=None))
    assert h.run(rid) == "done"
    h2 = Harness(str(tmp_path / "home"), PlannerProvider(steps_script(), []), config=fast_config())
    assert h2.planner.current_plan(rid) == ONE


def test_plan_errors():
    names = ["add", "mul"]
    assert plan_errors(ONE, names) == []
    short_end = mplan([pstep("add", spec_checks=["add"])])
    assert any("last step must list every spec check" in e for e in plan_errors(short_end, names))
    gap = mplan(
        [pstep("a", "m1", spec_checks=["add"]), pstep("b", "m3", spec_checks=names)],
        milestones=("m1", "m2", "m3"),
    )
    assert any("earlier milestone has none" in e for e in plan_errors(gap, names))
    order = mplan([pstep("a", "m2"), pstep("b", "m1", spec_checks=names)], milestones=("m1", "m2"))
    assert any("out of milestone order" in e for e in plan_errors(order, names))
    assert any(
        "effort" in e for e in plan_errors(mplan([pstep("a", effort="max", spec_checks=names)]), names)
    )


def test_locked_prefix():
    changed = mplan(
        [pstep("add", spec_checks=["add"], effort="high"), pstep("mul", spec_checks=["add", "mul"])]
    )
    assert locked_prefix_errors(ONE, changed, 1)
    assert locked_prefix_errors(ONE, changed, 0) == []


def test_effort_ladder():
    assert [escalate_effort("low", n) for n in range(4)] == ["low", "medium", "high", "high"]
    assert escalate_effort("xhigh", 2) == "xhigh"


def test_plan_schema_is_plain_json_schema():
    from urh.planner import PLAN_SCHEMA

    json.dumps(PLAN_SCHEMA)
    assert PLAN_SCHEMA["type"] == "object" and "steps" in PLAN_SCHEMA["properties"]


def test_missing_spec_checks_on_last_step_are_added_in_code_not_by_a_retry(make, hidden):
    forgot = mplan([pstep("add", spec_checks=["add"]), pstep("mul", spec_checks=[])])
    h, p = make(steps_script(), [forgot])
    rid = h.submit(make_spec(hidden, steps=None))
    assert h.run(rid) == "done"
    assert [c["role"] for c in h.journal.model_calls(rid)].count("manager") == 1
    assert h.planner.current_plan(rid).steps[-1].spec_checks == ["add", "mul"]


def test_later_steps_rerun_earlier_plan_checks_unless_retired():
    from urh.planner import regression_checks

    a = pstep("add")
    b = pstep("mul")
    c = pstep("div", retire_checks=[a.plan_checks[0]])
    plan = mplan([a, b, c])
    assert regression_checks(plan, 0) == []
    assert regression_checks(plan, 1) == a.plan_checks
    assert regression_checks(plan, 2) == b.plan_checks
    assert plan_errors(mplan([pstep("x", retire_checks=["nope"], spec_checks=["add"])]), ["add"])


def test_a_step_that_breaks_an_earlier_step_fails_its_gate(make, hidden):
    breaks_add = {
        "2": [
            [{"write": "add.py", "content": "x = 1\n"}, {"write": "mul.py", "content": MUL_PY}],
            [{"finish": "mul"}],
        ]
    }
    two = mplan([pstep("add", spec_checks=[]), pstep("mul", spec_checks=[])])
    h, p = make(steps_script(**breaks_add), [two, "no", "no"])
    rid = h.submit(make_spec(hidden, steps=None, max_repairs=0))
    assert h.run(rid) == "parked"
    first = h.journal.attempts(rid, 1)[0]
    assert first["status"] in ("fail", "superseded")
    assert any(f.startswith("regression1") for f in first["verdict"]["failures"])


def test_untrusted_plan_checks_send_the_step_back_to_the_planner(make, hidden):
    """A step decided only by planner checks the vetter cannot trust is replanned, not passed or parked."""
    first = mplan([pstep("add", spec_checks=[]), pstep("mul", spec_checks=["add", "mul"])])
    better = mplan(
        [
            pstep("add", instructions="Write add.py (v2)", spec_checks=[]),
            pstep("mul", spec_checks=["add", "mul"]),
        ]
    )
    script = steps_script()
    script["by_marker"] = {"(v2)": [[{"write": "add.py", "content": ADD_PY}], [{"finish": "add v2"}]]}
    h, p = make(script, [first, better], use_judge=False)
    calls = []

    def vetter(checks, parent_tree, candidate_tree, step_files, worker_written=()):
        calls.append(list(checks))
        return ("unsure", {}) if len(calls) == 1 else ("pass", {})

    h.vetter = vetter
    rid = h.submit(make_spec(hidden, steps=None))
    assert h.run(rid) == "done"
    assert [e["why"] for e in h.journal.events(rid) if e["kind"] == "plan"] == ["plan", "replan"]
    assert "cannot tell a broken step" in p.planner_prompts[1]
    assert len(calls) == 2  # the mul step has spec checks, so its plan checks are not vetted


def test_plan_shaped_failures():
    from urh.orchestrator import plan_shaped

    def f(*xs):
        return [{"verdict": {"failures": list(xs)}}]

    assert plan_shaped(f("missing file: mul.py"))
    assert plan_shaped(f("plan1: ImportError: cannot import name 'mul'", "no progress"))
    assert not plan_shaped(f("test_mul.py::test_mul"))
    assert not plan_shaped(f("missing file: mul.py", "test_mul.py::test_mul"))
    assert not plan_shaped([])


def test_plan_shaped_failure_replans_before_escalating(make, hidden):
    fixed = mplan(
        [
            pstep("add", spec_checks=["add"]),
            pstep("mul", instructions="Write mul.py (v2): multiply", spec_checks=["add", "mul"]),
        ]
    )
    # The worker never writes mul.py, so every failure names the missing file: a plan problem.
    script = steps_script(**{"2": [[{"write": "other.py", "content": "x = 1\n"}], [{"finish": "mul"}]]})
    script["by_marker"] = {"(v2)": [[{"write": "mul.py", "content": MUL_PY}], [{"finish": "mul v2"}]]}
    h, p = make(script, [ONE, fixed])
    rid = h.submit(make_spec(hidden, steps=None))
    assert h.run(rid) == "done"
    kinds = [e["kind"] for e in h.journal.events(rid)]
    assert "step_replanned" in kinds and "escalated" not in kinds


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
