import json
import os
import stat
import sys

import pytest

from urh.providers.base import ProviderUnavailable
from urh.providers.claude_cli import ClaudeCliProvider, parse_tool_answer, render_transcript

TOOLS = [
    {
        "name": "write_file",
        "description": "Write a file.",
        "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}},
    },
    {"name": "finish", "description": "Done.", "input_schema": {"type": "object"}},
]


def fake_cli(tmp_path, reply: dict, record: str) -> str:
    """A stand-in `claude` binary: records its argv and stdin, prints a canned JSON result."""
    path = tmp_path / "claude"
    path.write_text(
        f"#!{sys.executable}\n"
        "import json, sys\n"
        f"open({record!r}, 'w').write(json.dumps({{'argv': sys.argv[1:], 'stdin': sys.stdin.read()}}))\n"
        f"print(json.dumps({reply!r}))\n"
    )
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return str(path)


def test_structured_call_maps_schema_effort_and_cost(tmp_path):
    rec = str(tmp_path / "rec.json")
    reply = {
        "is_error": False,
        "result": "",
        "structured_output": {"a": 1},
        "total_cost_usd": 0.012,
        "usage": {"input_tokens": 10, "output_tokens": 5},
        "stop_reason": "end_turn",
    }
    p = ClaudeCliProvider(binary=fake_cli(tmp_path, reply, rec))
    resp = p.complete(
        {
            "model": "claude-opus-5-5",
            "system": [{"type": "text", "text": "SYS"}],
            "messages": [{"role": "user", "content": "plan it"}],
            "effort": "high",
            "response_schema": {"type": "object"},
        }
    )
    assert json.loads(resp.content[0]["text"]) == {"a": 1}
    assert resp.cost_usd == 0.012 and resp.usage["input_tokens"] == 10
    sent = json.loads(open(rec).read())
    argv = sent["argv"]
    assert argv[argv.index("--model") + 1] == "claude-opus-5-5"
    assert argv[argv.index("--effort") + 1] == "high"
    assert argv[argv.index("--tools") + 1] == ""  # the CLI's own tools stay off
    assert json.loads(argv[argv.index("--json-schema") + 1]) == {"type": "object"}
    assert sent["stdin"] == "plan it"


def test_tool_calls_are_emulated_as_canonical_blocks(tmp_path):
    rec = str(tmp_path / "rec.json")
    answer = {
        "text": "writing",
        "tool_calls": [
            {"name": "write_file", "input_json": '{"path": "a.py"}'},
            {"name": "finish", "input_json": "not json"},
        ],
    }
    reply = {"is_error": False, "structured_output": answer, "total_cost_usd": 0.001, "usage": {}}
    p = ClaudeCliProvider(binary=fake_cli(tmp_path, reply, rec))
    messages = [{"role": "user", "content": "STEP 1"}]
    resp = p.complete({"model": "claude-haiku-5-5", "system": "rules", "messages": messages, "tools": TOOLS})
    assert resp.stop_reason == "tool_use"
    uses = [b for b in resp.content if b["type"] == "tool_use"]
    assert [u["name"] for u in uses] == ["write_file", "finish"]
    assert uses[0]["input"] == {"path": "a.py"} and "_unparsed" in uses[1]["input"]
    argv = json.loads(open(rec).read())["argv"]
    system = argv[argv.index("--system-prompt") + 1]
    assert "write_file" in system and "input_json" in system
    schema = json.loads(argv[argv.index("--json-schema") + 1])
    assert schema["properties"]["tool_calls"]["items"]["properties"]["name"]["enum"] == [
        "write_file",
        "finish",
    ]


def test_transcript_renders_calls_and_results_append_only():
    m1 = [{"role": "user", "content": "STEP 1"}]
    m2 = m1 + [
        {
            "role": "assistant",
            "content": [{"type": "tool_use", "id": "t1", "name": "write_file", "input": {"path": "a.py"}}],
        },
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "wrote a.py"}]},
    ]
    t2 = render_transcript(m2)
    assert "TOOL CALL [t1] write_file" in t2 and "TOOL RESULT [t1]:\nwrote a.py" in t2
    m3 = m2 + [{"role": "assistant", "content": [{"type": "text", "text": "ok"}]}]
    assert render_transcript(m3).startswith(t2.rsplit("\n\nContinue", 1)[0])


def test_ids_are_unique_across_turns():
    a = parse_tool_answer(
        {"text": "", "tool_calls": [{"name": "finish", "input_json": "{}"}]},
        [{"role": "user", "content": "x"}],
    )
    b = parse_tool_answer(
        {"text": "", "tool_calls": [{"name": "finish", "input_json": "{}"}]},
        [{"role": "user", "content": "x"}, {"role": "assistant", "content": []}],
    )
    assert a[0]["id"] != b[0]["id"]


def test_cli_failures_are_transient(tmp_path):
    p = ClaudeCliProvider(binary=str(tmp_path / "missing-claude"))
    with pytest.raises(ProviderUnavailable):
        p.complete({"model": "m", "messages": [{"role": "user", "content": "x"}]})
    rec = str(tmp_path / "rec.json")
    p = ClaudeCliProvider(
        binary=fake_cli(tmp_path, {"is_error": True, "api_error_status": 529, "result": "x"}, rec)
    )
    with pytest.raises(ProviderUnavailable):
        p.complete({"model": "m", "messages": [{"role": "user", "content": "x"}]})


@pytest.mark.skipif(os.name == "nt", reason="posix shebang")
def test_harness_runs_end_to_end_on_the_cli_provider(tmp_path, hidden):
    """A scripted 'CLI' plays planner and worker through the real adapter, worker loop and gate."""
    from conftest import ADD_PY, fast_config, make_spec

    from urh.orchestrator import Harness

    script = tmp_path / "claude"
    plan = {
        "milestones": [{"id": "m1", "title": "add", "outline": "add works"}],
        "steps": [
            {
                "id": "add",
                "milestone": "m1",
                "title": "add",
                "instructions": "Write add.py",
                "expected_output": "add.py with add(a, b)",
                "files": ["add.py"],
                "plan_checks": [],
                "spec_checks": ["add", "mul"],
                "effort": "low",
            }
        ],
    }
    worker_turn = {
        "text": "",
        "tool_calls": [
            {"name": "write_file", "input_json": json.dumps({"path": "add.py", "content": ADD_PY})},
            {
                "name": "write_file",
                "input_json": json.dumps({"path": "mul.py", "content": "def mul(a, b):\n    return a * b\n"}),
            },
            {"name": "finish", "input_json": json.dumps({"summary": "done"})},
        ],
    }
    script.write_text(
        f"#!{sys.executable}\n"
        "import json, sys\n"
        "argv = sys.argv[1:]; sys.stdin.read()\n"
        "system = argv[argv.index('--system-prompt') + 1]\n"
        f"out = {plan!r} if 'planner of a headless' in system else {worker_turn!r}\n"
        "print(json.dumps({'is_error': False, 'structured_output': out, 'total_cost_usd': 0.001, 'usage': {}}))\n"
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    h = Harness(str(tmp_path / "home"), ClaudeCliProvider(binary=str(script)), config=fast_config())
    rid = h.submit(make_spec(hidden, steps=None))
    assert h.run(rid) == "done"
    calls = h.journal.model_calls(rid)
    assert {c["role"] for c in calls} == {"manager", "worker"}
    assert all(c["provider"] == "claude-cli" for c in calls)
    assert abs(h.journal.get_run(rid).spent_usd - 0.001 * len(calls)) < 1e-9


def test_cli_runs_from_an_empty_directory_not_the_callers(tmp_path, monkeypatch):
    rec = str(tmp_path / "rec.json")
    path = tmp_path / "claude"
    path.write_text(
        f"#!{sys.executable}\n"
        "import json, os, sys\n"
        f"open({rec!r}, 'w').write(json.dumps({{'cwd': os.getcwd(), 'ls': os.listdir('.')}}))\n"
        "print(json.dumps({'is_error': False, 'result': 'ok', 'usage': {}}))\n"
    )
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    monkeypatch.chdir(tmp_path)
    ClaudeCliProvider(binary=str(path)).complete(
        {"model": "m", "system": "s", "messages": [{"role": "user", "content": "hi"}]}
    )
    seen = json.load(open(rec))
    assert seen["cwd"] != str(tmp_path) and seen["ls"] == []
