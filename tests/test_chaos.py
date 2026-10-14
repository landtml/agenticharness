"""A small chaos run in CI: random SIGKILLs must never duplicate an effect or redo a verified step."""

import pytest

from urh.bench.chaos import FAULT_POINTS, run_trial, summarize


def test_random_kills_never_duplicate_effects_or_redo_verified_steps():
    trials = [
        run_trial(seed, steps=3, lease_ttl=1.0, effect_delay=0.3, max_kills=2, kill_window=(0.3, 2.0))
        for seed in range(3)
    ]
    s = summarize(trials)
    assert s["completed"] == 3
    assert s["duplicate_effects"] == 0
    assert s["redone_verified_steps"] == 0


@pytest.mark.parametrize("fault", FAULT_POINTS)
def test_kill_at_each_commit_boundary_finishes_without_redoing_verified_work(fault):
    t = run_trial(5, steps=2, lease_ttl=1.0, effect_delay=0.0, max_kills=0, kill_window=(0, 0), fault=fault)
    assert t["kills"] == 1, "the fault point never fired"
    assert t["completed"]
    assert t["duplicate_effects"] == 0
    assert t["redone_verified_steps"] == 0
