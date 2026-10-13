import pytest

from urh.blobs import BlobStore
from urh.gateway import (
    CallContext,
    CircuitBreaker,
    ModelGateway,
    ProviderDown,
    ProviderResponse,
    ProviderUnavailable,
    cost_usd,
)
from urh.journal import BudgetExceeded, Journal

REQ = {"system": "be brief", "messages": [{"role": "user", "content": "hi"}], "max_tokens": 256}


class FakeProvider:
    name = "anthropic"

    def __init__(self, failures=0, always_down=False, served_model=None):
        self.failures = failures
        self.always_down = always_down
        self.served_model = served_model
        self.requests = []

    def complete(self, request):
        self.requests.append(request)
        if self.always_down or len(self.requests) <= self.failures:
            raise ProviderUnavailable("503 from fake")
        return ProviderResponse(
            content=[{"type": "text", "text": "ok"}],
            stop_reason="end_turn",
            usage={"input_tokens": 100, "output_tokens": 50},
            model=self.served_model or request["model"],
        )


@pytest.fixture
def j(tmp_path):
    return Journal(tmp_path / "j.sqlite")


@pytest.fixture
def blobs(tmp_path):
    return BlobStore(tmp_path / "blobs")


def _run(j, budget=1.0):
    rid, _ = j.create_run({"goal": "x"}, ModelGateway.default_pins(), budget)
    return rid, j.acquire_lease(rid, "p", ttl=60)


def _ctx(rid, epoch, role="worker", call_index=0):
    return CallContext(rid, epoch, 0, 1, role, call_index)


def _gw(j, blobs, provider, **kw):
    kw.setdefault("backoff_s", 0)
    kw.setdefault("sleep", lambda s: None)
    return ModelGateway(j, blobs, provider, **kw)


def test_haiku_cost_at_base_rates():
    usage = {"input_tokens": 10_000, "output_tokens": 10_000}
    assert cost_usd("claude-haiku-5-5", usage) == pytest.approx(0.006)


def test_haiku_long_prompt_tier_applies_above_100k():
    # Above 100k prompt tokens Haiku 5.5 is billed at $0.50 / $2.50 per MTok.
    assert cost_usd("claude-haiku-5-5", {"input_tokens": 1_000_000, "output_tokens": 1_000_000}) == pytest.approx(3.00)
    assert cost_usd("claude-haiku-5-5", {"input_tokens": 100_000, "output_tokens": 1_000_000}) == pytest.approx(0.51)


def test_opus_million_in_million_out_costs_24():
    assert cost_usd("claude-opus-5-5", {"input_tokens": 1_000_000, "output_tokens": 1_000_000}) == pytest.approx(24.0)


def test_cache_read_is_priced_per_model():
    assert cost_usd("claude-opus-5-5", {"cache_read_input_tokens": 1_000_000}) == pytest.approx(0.20)
    assert cost_usd("claude-haiku-5-5", {"cache_read_input_tokens": 1_000}) == pytest.approx(0.01 * 1_000 / 1e6)


def test_successful_call_is_logged_and_settled(j, blobs):
    rid, epoch = _run(j)
    resp = _gw(j, blobs, FakeProvider()).call(_ctx(rid, epoch), j.get_run(rid).pins, REQ)
    assert resp.stop_reason == "end_turn"

    [row] = j.model_calls(rid)
    assert row["status"] == "ok"
    assert row["input_tokens"] == 100 and row["output_tokens"] == 50
    expected = cost_usd("claude-haiku-5-5", {"input_tokens": 100, "output_tokens": 50})
    assert row["cost_usd"] == pytest.approx(expected)

    run = j.get_run(rid)
    assert run.reserved_usd == pytest.approx(0)
    assert run.spent_usd == pytest.approx(expected)


def test_gateway_sets_model_from_pins_not_caller(j, blobs):
    rid, epoch = _run(j)
    provider = FakeProvider()
    gw = _gw(j, blobs, provider)
    pins = ModelGateway.default_pins()
    gw.call(_ctx(rid, epoch, "worker", 0), pins, {**REQ, "model": "claude-opus-5-5"})
    gw.call(_ctx(rid, epoch, "manager", 1), pins, {**REQ, "model": "claude-haiku-5-5"})
    assert provider.requests[0]["model"] == "claude-haiku-5-5"
    assert provider.requests[1]["model"] == "claude-opus-5-5"


def test_always_down_raises_provider_down_after_retries(j, blobs):
    rid, epoch = _run(j)
    provider = FakeProvider(always_down=True)
    gw = _gw(j, blobs, provider, retries=2)
    with pytest.raises(ProviderDown):
        gw.call(_ctx(rid, epoch), j.get_run(rid).pins, REQ)
    assert len(provider.requests) == 3
    [row] = j.model_calls(rid)
    assert row["status"] == "error"
    assert j.get_run(rid).reserved_usd == pytest.approx(0)


def test_transient_failure_then_success(j, blobs):
    rid, epoch = _run(j)
    provider = FakeProvider(failures=1)
    resp = _gw(j, blobs, provider, retries=2).call(_ctx(rid, epoch), j.get_run(rid).pins, REQ)
    assert resp.content == [{"type": "text", "text": "ok"}]
    assert len(provider.requests) == 2
    assert [r["status"] for r in j.model_calls(rid)] == ["ok"]


def test_budget_too_small_blocks_the_provider_call(j, blobs):
    rid, epoch = _run(j, budget=0.00001)
    provider = FakeProvider()
    with pytest.raises(BudgetExceeded):
        _gw(j, blobs, provider).call(_ctx(rid, epoch), j.get_run(rid).pins, REQ)
    assert provider.requests == []


def test_model_drift_is_refused(j, blobs):
    rid, epoch = _run(j)
    provider = FakeProvider(served_model="claude-sonnet-5-5")
    with pytest.raises(ProviderDown, match="provider served claude-sonnet-5-5"):
        _gw(j, blobs, provider).call(_ctx(rid, epoch), j.get_run(rid).pins, REQ)
    [row] = j.model_calls(rid)
    assert row["status"] == "error"


def test_circuit_breaker_opens_after_threshold():
    b = CircuitBreaker(threshold=2, cooldown_s=60)
    assert b.allow() is True
    b.record(False)
    b.record(False)
    assert b.allow() is False
