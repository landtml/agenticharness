# Round 2: parks are failures

Frederik's bar: a run that needs a person is a chatbot, not an agent. This round treats every park as a
failure. It sorts them into **avoidable** parks (the harness could have finished) and **needed** parks
(finishing would be a lie: the work is impossible as specified, or the money is gone). The goal is zero
avoidable parks with zero wrong finishes.

| Scenario (`python -m urh.bench.parks`) | Round-1 policy | Current policy | Correct outcome |
| --- | --- | --- | --- |
| clean | done | done | done |
| budget shortfall | parked (budget) | done, topped up within allowance | done |
| provider outage | parked (outage) | done, self-woke after the breaker closed | done |
| step no script check covers | parked (unsure) | done, blind judge decided | done |
| hard step: repairs exhausted | parked | done, escalation model fixed it | done |
| repair repeats the failed tree | parked | done, counted as a failure, then escalation | done |
| hopeless step (escalation fails too) | parked | **parked** | parked |
| runaway cost beyond every top-up | parked | **parked** | parked |
| **avoidable parks / wrong finishes** | **5 / 0** | **0 / 0** | |

Raw rows: `r2-parks.json`. The bench uses the scripted provider. It measures the harness's *decisions*,
not model quality.

## What changed

- **Budget**: `auto_topup_usd` × `max_auto_topups` lets a run grow within a fixed allowance. A run that
  needs more than that still parks. The global spend cap still holds.
- **Outages**: an outage park carries `wake_at`. `run_pending` answers it with an `auto:` answer once the
  time has passed *and* the breaker is closed, so a wake never just parks again. Auto answers are not
  human touches.
- **Unsure**: `judge.py` asks the judge role for pass, fail or unsure under a JSON schema. It sees the step
  and the changed files fenced as untrusted, never the worker's summary. An unavailable judge leaves the
  step unsure.
- **Exhausted repairs**: one more attempt on the `escalation` role (the manager's model by default)
  before parking. A repair that reproduces a failed tree no longer parks at once. It counts as a failure,
  so it flows into the same path.
- **Model pins**: a role missing from `models` follows its sibling (judge follows worker, escalation
  follows manager). A vendor-only config no longer falls back to a Claude ID for those roles. The bench
  test caught this.
- **Metrics**: `urh stats` reports park_rate, human_touches, headless_done, auto_resolved_parks,
  cost_per_done_usd, calls_per_done, calls_by_role and cache_hit_ratio.

## Not measured yet

- **The judge's own false-accept rate.** The scripted judge always says pass. A judge that waves bad work
  through turns avoidable parks into wrong finishes, the worse failure. The next round audits it on the
  mutant corpora the way round 1 audited the script gate.
- **Live park rate.** This needs Haiku 5.5 workers on the bench tasks, which waits on the planner branch
  merging round 2. The planner adds a replan step between escalation and parking.
