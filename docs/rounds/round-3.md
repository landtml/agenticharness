# Round 3: a judge you can trust, and a runtime that needs nobody

Round 2 cut avoidable parks by letting a model judge decide steps no script covers. A judge that waves
bad work through turns a park into a wrong finish, which is worse, so this round audits the judge the way
round 1 audited the script gate. Then it builds the piece the product needs next: runs that start
themselves.

## The judge, measured live (Haiku 5.5 as judge)

Each broken version of the slug step goes to the judge alone, as if no script check applied. It must
reject all of them and accept the reference. `unsure` counts as not accepted.

| Judge | Hand-written mutants (15) | Blind Haiku mutants (20) | Reference |
| --- | --- | --- | --- |
| v1, as first measured | 9 accepted (60%) | 0 accepted, **invalid**: the files' comments named the bug | accepted |
| v1, blind corpus scrubbed | | **10 accepted (50%)** | accepted |
| v2 | 0 and 1 accepted (two runs) | 0 accepted | accepted, every run |

v2 pooled: **1 false accept in 50** (95% CI 0.4–10.5%) for $0.14 across all six audit runs. Raw rows:
`r3-judge-audit.json`.

**Why v1 failed.** It saw only the current step. Step 2 says "keep step 1 behaviour unchanged" without
restating step 1, so mutants that broke step-1 rules (no stripping, dropped digits) looked fine. v2 gets
the goal, the constraints and every earlier step's instructions as *standing requirements*. It must also
trace the code by hand on every stated example and on one edge case per rule. It is told to ignore
what the code says about itself.

**The corpus leaked.** Round 1's blind mutants carried header comments naming their bug. The script gate
never reads comments, so the leak was invisible until a model read the files. The labels now live in
`mutants_blind_labels.json`. Lesson for every future corpus: an artifact under review must not carry
its own label.

## Headless runtime

- `urh/cron.py`: five-field UTC cron with aliases, both-day-fields-mean-either, and Feb 29.
- `urh/runtime.py`: cron and webhook triggers, self-waking parks, and a bounded thread pool.
  - A slot's run is created under `trigger:<id>:<slot>` *before* the trigger advances, so a crash
    between the two cannot fire twice (tested with a kill injected at that point).
  - Missed slots coalesce into one run that carries the count.
  - Webhooks need an HMAC-SHA256 signature. The delivery id dedupes redeliveries. The body reaches models
    only as fenced untrusted input in the pinned prefix, so it can't close the fence.
- `urh/server.py`: `urh serve` runs the daemon plus an HTTP API: runs, inbox (only parks that will not
  wake themselves), triggers, stats, `/hooks/<name>`. A bearer token is required, because a spec's check
  commands run on the host.
- CLI: `urh serve`, `urh daemon` (now fires triggers too), `urh trigger add-cron|add-webhook|list|rm|enable|disable`.

## Bugs the runtime surfaced

- **Blob store race.** Temp files were named by process id, so two threads storing the same blob
  collided and one run crashed. Temp files are now unique per writer.
- **Crash loops.** A run whose drive raised released its lease and was immediately runnable again, so a
  deterministic harness bug would spin forever. Crashes are journaled, and the third parks the run as
  `harness_error` with the last error.

## Next

1. Live park rate and cost per verified run on the planner's bench tasks, against a plain loop.
2. Grow the judge audit beyond one task: the gate thread's blind corpus covers 8.
3. ~~Outbound park notifications~~: done in `notify.py`. Parks that need a person go out through a journaled
   outbox (webhook, Slack-style or file), at least once, with backoff and a cap.
