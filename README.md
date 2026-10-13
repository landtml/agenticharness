# Upper-Right Harness (URH)

A durable, headless agent orchestrator. Claude Opus 5.5 is the manager that plans steps for novel tasks;
Claude Haiku 5.5 workers do each step in a fresh context; script gates the worker cannot touch decide when a
step is done. Everything that must survive a `kill -9` lives in a SQLite journal and a per-run git repository.
Models are reached only through the Anthropic API.

The design follows the "Upper-Right Harness" recipe: journal first, then gates, idempotent effects and the
park, then the gateway and budget, then context layout, then the manager.

## Quick start

```bash
pip install -e '.[dev]'
python -m pytest -q                    # 50 offline tests, including a real SIGKILL resume test

export ANTHROPIC_API_KEY=...
urh submit examples/slug/spec.json     # prints a run id
urh run                                # drives every runnable run until done, failed or parked
urh status
urh parks                              # questions waiting for a person
urh answer <park_id> "approve"         # answers are claimed once, then the run is requeued
urh calls <run_id>                     # model-call log: tokens, cache hits, dollars
urh daemon --interval 5                # headless: keep driving runnable runs
```

`python -m pytest -m live tests/live` drives real Haiku 5.5 workers through the slug example (a few cents).

## How a step runs

1. The run's lease is taken with a new **epoch**. A heartbeat renews it; every journal write that moves the
   run is fenced on that epoch, so a stalled process that lost the lease cannot advance the run.
2. The **manager** picks the step: code when the spec lists steps, one Opus call per step otherwise. The
   decision is journaled before the step runs, so a resume reuses it.
3. The **context assembler** builds a byte-stable cached prefix (rules, pinned goal, constraints, facts) and a
   per-step message. Repair notes carry capped gate output fenced as untrusted data.
4. The **worker** (Haiku 5.5) gets bash, read/write/list file tools and `propose_effect`, confined to a private
   folder for this epoch. Real paths are rewritten to `/work`; the git repo and hidden tests are outside it.
   Commands run with a scrubbed environment and, where the kernel allows, no network.
5. Every model call goes through the **gateway**: model and provider come from the run's pins, the worst-case
   cost is reserved against the run's one budget before the call and settled after, and the call is logged
   with tokens, cache reads and writes, latency and blob references. Outages retry, then trip a circuit
   breaker and park the run.
6. The workspace is snapshotted to an unverified commit and the **gate** runs the spec's checks on a
   throwaway export with the hidden tests copied in. Changes to protected paths fail. No applicable check
   means `unsure`, which parks.
7. **pass**: the commit is promoted (compare-and-swap on `refs/heads/verified`), the journal advances, and the
   step's held effects fire. **fail**: a bounded repair from the failed work; an attempt that reproduces a
   failed tree parks as no progress. **unsure**, budget, outage, exhausted repairs: park.

## Effects

The worker proposes effects; it never fires them. The **effect guard** derives the idempotency key from run,
step and effect index, records intent, and holds the effect until the step verifies. On flush it dispatches
with the key and the epoch as a fencing token, and records the result. After a crash it reads back before any
retry, re-sends only with a key, and parks anything with neither a key nor a read-back. Irreversible effects
park for approval. Effects from failed attempts are discarded unsent.

## Durability (D1)

A crash costs the step in flight. `tests/test_kill9.py` kills the harness with SIGKILL during a step-2 model
call, then starts a new process: step 1's calls are not repeated, its effect fires once, the lost call is
written off at its reservation, and step 2 re-runs once. Call-level replay (D2) is deliberately not built.

## Layout

| Module | Role |
| --- | --- |
| `journal.py` | SQLite (WAL) journal: runs, pins, leases, budget, attempts, verdicts, effects, parks, model calls |
| `checkpoint.py` | Per-run bare git repo, per-epoch workspaces, commit on gate pass, CAS promotion |
| `gateway.py` | Anthropic provider, pricing, reservation, call log, retries and circuit breaker |
| `effects.py` | Effect guard and adapters (outbox file, webhook, unkeyed) |
| `gate.py` | Script gate and mutant-corpus audit |
| `worker.py` | Haiku 5.5 tool loop and confined workspace tools |
| `manager.py` | Code manager and Opus 5.5 manager |
| `context.py` | Stable prefix and per-step messages |
| `orchestrator.py` | The control loop: leases, verdict routing, repairs, parks, admission |
| `sandbox.py` | Scrubbed, timed, network-isolated command runner |
| `testing.py` | Scripted provider for deterministic tests and offline demos |

## Not built yet

Cue-triggered memory, a model judge for checks no script decides, a chat inbox and scheduled wake-ups for
parked runs, cross-run rate limits beyond max active runs and a global spend cap, a mount-namespace
`/work` sandbox, call replay (D2), and the offline release loop. Postgres can replace SQLite when runs
span machines.
