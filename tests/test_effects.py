from pathlib import Path

import pytest

from urh.effects import EffectGuard, Fence, OutboxFileAdapter, StaleFence, UnkeyedCommandAdapter
from urh.journal import Journal


@pytest.fixture
def j(tmp_path):
    return Journal(tmp_path / "j.sqlite")


def _run(j):
    rid, _ = j.create_run({"goal": "x"}, {"provider": "anthropic"}, 1.0)
    return rid, j.acquire_lease(rid, "p", ttl=60)


def _deliveries(outbox: Path) -> list[str]:
    log = outbox / "deliveries.log"
    return log.read_text().split() if log.exists() else []


def test_keyed_effect_is_delivered_exactly_once(tmp_path, j):
    rid, epoch = _run(j)
    outbox = tmp_path / "outbox"
    guard = EffectGuard(j, [OutboxFileAdapter(str(outbox))])
    key = guard.propose(rid, epoch, 0, 0, "outbox_file", {"msg": "hi"})

    first = guard.flush(rid, epoch, 0)
    second = guard.flush(rid, epoch, 0)

    assert first.done == [key] and second.done == [key]
    assert _deliveries(outbox) == [key]
    assert j.effects(rid, 0)[0]["status"] == "done"


def test_same_step_and_index_give_same_key_and_one_row(tmp_path, j):
    rid, epoch = _run(j)
    guard = EffectGuard(j, [OutboxFileAdapter(str(tmp_path / "outbox"))])
    k1 = guard.propose(rid, epoch, 2, 0, "outbox_file", {"msg": "a"})
    k2 = guard.propose(rid, epoch, 2, 0, "outbox_file", {"msg": "a"})
    assert k1 == k2
    assert len(j.effects(rid)) == 1


def test_crash_after_dispatch_reads_back_without_resending(tmp_path, j):
    rid, epoch = _run(j)
    outbox = tmp_path / "outbox"
    adapter = OutboxFileAdapter(str(outbox))
    guard = EffectGuard(j, [adapter])
    key = guard.propose(rid, epoch, 0, 0, "outbox_file", {"msg": "hi"})
    payload = j.effects(rid, 0)[0]["payload"]

    j.mark_effect(rid, epoch, key, "dispatching")
    adapter.dispatch(key, payload, Fence(rid, epoch))  # the write landed, then the process died

    result = guard.flush(rid, epoch, 0)
    assert result.done == [key]
    assert _deliveries(outbox) == [key]
    assert j.effects(rid, 0)[0]["status"] == "done"


def test_unkeyed_effect_is_parked_and_never_dispatched(tmp_path, j):
    rid, epoch = _run(j)
    guard = EffectGuard(j, [UnkeyedCommandAdapter()])
    key = guard.propose(rid, epoch, 0, 0, "unkeyed", {"cmd": "drop table x"})

    result = guard.flush(rid, epoch, 0)

    assert [k for k, _ in result.parked] == [key]
    assert result.done == []
    assert j.effects(rid, 0)[0]["status"] == "parked"
    assert not any(e["kind"] == "effect_dispatching" for e in j.events(rid))


def test_irreversible_payload_waits_for_approval(tmp_path, j):
    rid, epoch = _run(j)
    outbox = tmp_path / "outbox"
    guard = EffectGuard(j, [OutboxFileAdapter(str(outbox))])
    key = guard.propose(rid, epoch, 0, 0, "outbox_file", {"irreversible": True, "msg": "send"})

    first = guard.flush(rid, epoch, 0)
    assert [k for k, _ in first.parked] == [key]
    assert _deliveries(outbox) == []

    second = guard.flush(rid, epoch, 0, approved={key})
    assert second.done == [key]
    assert _deliveries(outbox) == [key]


def test_stale_epoch_is_fenced_by_receiver(tmp_path):
    adapter = OutboxFileAdapter(str(tmp_path / "outbox"))
    adapter.dispatch("key-new", {}, Fence("run_x", 2))
    with pytest.raises(StaleFence):
        adapter.dispatch("key-old", {}, Fence("run_x", 1))


def test_unknown_kind_is_parked_with_no_adapter(j):
    rid, epoch = _run(j)
    guard = EffectGuard(j, [])
    key = guard.propose(rid, epoch, 0, 0, "carrier_pigeon", {})

    result = guard.flush(rid, epoch, 0)

    assert result.parked == [(key, "no adapter for carrier_pigeon")]
