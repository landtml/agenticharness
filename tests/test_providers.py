"""The provider layer is model-agnostic: one canonical format, adapters translate, roles map to any model."""

import json

import pytest
from conftest import fast_config, good_script, make_spec

from urh.blobs import BlobStore
from urh.gateway import CallContext, ModelGateway
from urh.journal import Journal
from urh.orchestrator import Harness
from urh.pricing import FALLBACK_PRICE, Price, PriceBook
from urh.providers.anthropic import to_messages_api
from urh.providers.base import ProviderResponse
from urh.providers.openai_compat import from_chat_completions, to_chat_completions
from urh.testing import ScriptedProvider

CANONICAL = {
    "model": "some/model",
    "max_tokens": 1000,
    "system": [{"type": "text", "text": "rules", "cache_control": {"type": "ephemeral"}}],
    "messages": [
        {"role": "user", "content": "do it"},
        {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "ok"},
                {"type": "tool_use", "id": "t1", "name": "bash", "input": {"command": "ls"}},
            ],
        },
        {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": "t1", "content": "a.py", "is_error": False},
                {"type": "text", "text": "continue"},
            ],
        },
    ],
    "tools": [{"name": "bash", "description": "run", "input_schema": {"type": "object", "properties": {}}}],
    "effort": "low",
    "response_schema": {"type": "object"},
}


def test_anthropic_adapter_maps_hints_to_output_config():
    out = to_messages_api(CANONICAL)
    assert "effort" not in out and "response_schema" not in out
    assert out["output_config"] == {
        "effort": "low",
        "format": {"type": "json_schema", "schema": {"type": "object"}},
    }


def test_openai_compatible_translation_round_trip():
    body = to_chat_completions(CANONICAL)
    roles = [m["role"] for m in body["messages"]]
    assert roles == ["system", "user", "assistant", "tool", "user"]
    assert body["messages"][2]["tool_calls"][0]["function"] == {
        "name": "bash",
        "arguments": '{"command": "ls"}',
    }
    assert body["messages"][3] == {"role": "tool", "tool_call_id": "t1", "content": "a.py"}
    assert body["tools"][0]["function"]["name"] == "bash"
    assert body["response_format"]["json_schema"]["schema"] == {"type": "object"}

    resp = from_chat_completions(
        {
            "model": "some/model",
            "choices": [
                {
                    "finish_reason": "tool_calls",
                    "message": {
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "c1",
                                "function": {
                                    "name": "write_file",
                                    "arguments": '{"path": "a", "content": "b"}',
                                },
                            }
                        ],
                    },
                }
            ],
            "usage": {
                "prompt_tokens": 120,
                "completion_tokens": 30,
                "prompt_tokens_details": {"cached_tokens": 100},
                "cost": 0.0042,
            },
        }
    )
    assert resp.stop_reason == "tool_use"
    assert resp.content == [
        {"type": "tool_use", "id": "c1", "name": "write_file", "input": {"path": "a", "content": "b"}}
    ]
    assert resp.usage["input_tokens"] == 20 and resp.usage["cache_read_input_tokens"] == 100
    assert resp.cost_usd == pytest.approx(0.0042)


def test_price_book_overrides_and_pessimistic_fallback():
    book = PriceBook({"vendor/open-model": Price(input=1.0, output=2.0)})
    assert book.cost(
        "vendor/open-model", {"input_tokens": 1_000_000, "output_tokens": 1_000_000}
    ) == pytest.approx(3.0)
    unknown = book.cost("never/heard-of", {"input_tokens": 1_000_000})
    assert unknown == pytest.approx(FALLBACK_PRICE.input)


class _ReportsCost:
    name = "anthropic"

    def complete(self, request):
        return ProviderResponse(
            [{"type": "text", "text": "hi"}],
            "end_turn",
            {"input_tokens": 10, "output_tokens": 5},
            request["model"],
            cost_usd=0.123,
        )


def test_provider_reported_cost_wins(tmp_path):
    j, b = Journal(tmp_path / "j.sqlite"), BlobStore(tmp_path / "b")
    rid, _ = j.create_run({"goal": "x"}, ModelGateway.default_pins(), 1.0)
    epoch = j.acquire_lease(rid, "p", 10)
    gw = ModelGateway(j, b, _ReportsCost())
    gw.call(
        CallContext(rid, epoch, 0, 1, "worker", 0), j.get_run(rid).pins, {"max_tokens": 10, "messages": []}
    )
    assert j.model_calls(rid)[0]["cost_usd"] == pytest.approx(0.123)


def test_unnamed_roles_follow_their_sibling_not_the_default_vendor(tmp_path):
    h = Harness(str(tmp_path / "home"), ScriptedProvider(good_script()), config=fast_config())
    pins = h.gateway.pins_for({"worker": "x/small", "manager": "x/big"})
    assert pins["models"]["judge"] == "x/small"
    assert pins["models"]["escalation"] == "x/big"


def test_roles_map_to_any_model_ids(tmp_path, hidden):
    models = {"manager": "vendor/big-planner", "worker": "vendor/small-coder", "judge": "vendor/small-coder"}
    h = Harness(
        str(tmp_path / "home"),
        ScriptedProvider(good_script()),
        config=fast_config(models=models),
        prices=PriceBook({"vendor/small-coder": Price(input=0.05, output=0.2)}),
    )
    rid = h.submit(make_spec(hidden))
    assert h.run(rid) == "done"
    assert h.journal.get_run(rid).pins["models"] == {**models, "escalation": "vendor/big-planner"}
    calls = h.journal.model_calls(rid)
    assert {c["model"] for c in calls} == {"vendor/small-coder"}
    assert all(c["cost_usd"] > 0 for c in calls)
    # The canonical request never carries vendor-specific fields.
    req = json.loads(h.blobs.get_bytes(calls[0]["request_blob"]))
    assert "output_config" not in req and req["model"] == "vendor/small-coder"
