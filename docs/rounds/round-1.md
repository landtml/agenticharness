# Round 1: durability and gate, measured offline

Scored against the outcome table in the Upper-Right Harness recipe. All numbers come from this
repository's benches, run with the scripted provider. No live model is involved yet; the live
Haiku 5.5 run comes next.

| Outcome (recipe) | Target | Round 1 | Evidence |
| --- | --- | --- | --- |
| Duplicate side effects under injected faults | 0 on keyed writes | **0** in 30 random-kill trials (53 SIGKILLs) and 6 fault-point trials | `r1-chaos.json`, `tests/test_chaos.py` |
| Work redone after `kill -9` | the step in flight (D1) | **0 verified steps redone**; 30% of worker calls were in aborted in-flight attempts (the D1 price at this kill rate) | `r1-chaos.json` |
| Effect interrupted between delivery and journal | settled by read-back, no resend | **settled by read-back** (fault point `effect_delivered`) | `tests/test_chaos.py` |
| Gate false-accept rate, hand-written mutants | measured, falling | **27% → 0%** (4/15 → 0/15; 95% CI 0–20%) | `tests/test_gate_audit.py` |
| Gate false-accept rate, blind mutant family | measured, falling | **95% → 0%** (19/20 → 0/20; 95% CI 0–16%) | `r1-gate-audit-blind.json` |
| Gate false-withhold of correct work | low | reference implementation accepted in every audit | same |

## What changed because of the measurements

- Fault injection at six commit boundaries found two resume bugs. A kill between ref promotion and
  `complete_step` left the run unable to finish, and a kill after a pass verdict redid a verified step.
  Resume now adopts a recorded pass verdict and finishes the commit. It also rolls the verified ref back
  when the ref points at a commit no gate passed.
- The example gate's example-based tests accepted almost every plausible bug that a blind Haiku 5.5 agent
  wrote. Seeded random-input checks against a hidden oracle, plus invariants (charset, idempotence), closed
  the gap on both corpora. This confirms the recipe's warning: a gate's rate belongs to one gate and one
  mutant family, so keep growing the corpus.

## Next

1. A live run with Haiku 5.5 workers and an Opus 5.5 manager through the CLI provider: cost per verified
   outcome, calls per outcome and cache hit rate, against a plain loop on the same tasks.
2. Repairs that converge on multi-milestone tasks (the recipe's round-3 failure mode).
3. Admission: rate and spend ceilings across runs, and a scheduled wake for answered parks.
