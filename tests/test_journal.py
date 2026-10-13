import threading
import time

import pytest

from urh.journal import BudgetExceeded, Journal, LeaseLost


@pytest.fixture
def j(tmp_path):
    return Journal(tmp_path / "j.sqlite")


def _run(j, budget=1.0, dedupe=None):
    rid, _ = j.create_run({"goal": "x"}, {"provider": "anthropic"}, budget, dedupe_key=dedupe)
    return rid


def test_dedupe_key_maps_to_existing_run(j):
    a, created_a = j.create_run({"goal": "x"}, {}, 1.0, dedupe_key="webhook-42")
    b, created_b = j.create_run({"goal": "x"}, {}, 1.0, dedupe_key="webhook-42")
    assert a == b and created_a and not created_b


def test_lease_is_exclusive_until_expiry_and_fences_old_holder(j):
    rid = _run(j)
    e1 = j.acquire_lease(rid, "p1", ttl=0.2)
    assert e1 == 1
    assert j.acquire_lease(rid, "p2", ttl=10) is None
    time.sleep(0.25)
    e2 = j.acquire_lease(rid, "p2", ttl=10)
    assert e2 == 2
    with pytest.raises(LeaseLost):
        j.event(rid, e1, "stale_write")
    with pytest.raises(LeaseLost):
        j.complete_step(rid, e1, 0, "deadbeef")
    j.event(rid, e2, "fresh_write")


def test_budget_reservation_denies_overrun_and_counts_denials(j):
    rid = _run(j, budget=0.01)
    epoch = j.acquire_lease(rid, "p", 10)
    call = {
        "step_index": 0,
        "attempt": 1,
        "call_index": 0,
        "role": "worker",
        "provider": "anthropic",
        "model": "claude-haiku-5-5",
    }
    cid = j.reserve(rid, epoch, call, 0.008)
    with pytest.raises(BudgetExceeded):
        j.reserve(rid, epoch, call, 0.005)
    j.settle(cid, 0.001, {"input_tokens": 10})
    run = j.get_run(rid)
    assert run.reserved_usd == pytest.approx(0) and run.spent_usd == pytest.approx(0.001) and run.denials == 1
    j.reserve(rid, epoch, call, 0.005)  # fits after settling


def test_stale_reservations_are_written_off_on_resume(j):
    rid = _run(j)
    e1 = j.acquire_lease(rid, "p", 10)
    call = {
        "step_index": 0,
        "attempt": 1,
        "call_index": 0,
        "role": "worker",
        "provider": "anthropic",
        "model": "claude-haiku-5-5",
    }
    j.reserve(rid, e1, call, 0.003)
    e2 = j.acquire_lease(rid, "p", 10)
    assert j.release_stale_reservations(rid, e2) == pytest.approx(0.003)
    run = j.get_run(rid)
    assert run.reserved_usd == pytest.approx(0) and run.spent_usd == pytest.approx(0.003)


def test_parked_answer_is_claimed_exactly_once_under_a_race(tmp_path):
    path = tmp_path / "j.sqlite"
    j = Journal(path)
    rid = _run(j)
    epoch = j.acquire_lease(rid, "p", 10)
    pid = j.park(rid, epoch, 0, "unsure", "ok?")
    j.answer_park(pid, "yes")
    claims: list[int] = []

    def racer():
        jj = Journal(path)  # separate connection, like separate processes
        claims.append(len(jj.claim_answers(rid, epoch, "racer")))

    threads = [threading.Thread(target=racer) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(claims) == [0] * 7 + [1]


def test_refuses_journal_from_newer_schema(tmp_path):
    j = Journal(tmp_path / "j.sqlite")
    with j.tx() as c:
        c.execute("UPDATE meta SET value='999' WHERE key='schema_version'")
    j.close()
    with pytest.raises(RuntimeError, match="newer"):
        Journal(tmp_path / "j.sqlite")


def test_plan_step_first_writer_wins(j):
    rid = _run(j)
    e = j.acquire_lease(rid, "p", 10)
    first = j.plan_step(rid, e, 0, {"title": "a"}, "manager")
    second = j.plan_step(rid, e, 0, {"title": "b"}, "manager")
    assert first == second == {"title": "a"}
