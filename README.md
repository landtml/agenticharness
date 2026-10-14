# agenticharness

The Upper-Right Harness (URH): a durable, headless agent orchestrator. A Claude Opus 5.5 manager plans work,
Claude Haiku 5.5 workers do it (build, code, test, lint, scout, scaffold), script gates decide when work is
done, and a journal lets any run survive `kill -9` without redoing verified steps.

The harness is model-agnostic: providers are adapters behind one interface (`urh.providers`), and which
model plays manager, worker or judge is configuration (`--models`, `--prices`). This repository develops
and tests with Claude Opus 5.5 and Claude Haiku 5.5 through Anthropic; an OpenAI-compatible adapter
(OpenAI, OpenRouter, local servers) ships too but is not exercised against real endpoints here.

## Layout

| Path | Contents |
| --- | --- |
| `src/` | Python packages (the harness lives in `src/urh`) |
| `tests/` | pytest suites; `tests/live` calls the real API and is opt-in |
| `examples/` | Task specs with seed files and hidden gate tests |
| `docs/` | Design notes |
| `.github/workflows/` | CI for Python, TypeScript and Rust on every push to `main` and every pull request |
| `ts/` | TypeScript workspace (Node 22, strict, `npm run check`) |
| `rust/` | Cargo workspace; `crates/urh-core` holds Rust components |
| `scripts/` | Repo scripts, including the Claude Code cloud SessionStart hook |

`CLAUDE.md` holds the ground rules every Claude session and Haiku worker follows in this repo.

## Development

```bash
make setup                          # .venv with the package, npm install, cargo fetch
make check                          # everything CI runs: Python, TypeScript, Rust
python -m pytest -m live tests/live # real-model tests; need ANTHROPIC_API_KEY
```

Python 3.11 or newer (CI uses 3.12), Node 22, stable Rust. Lint settings are in `ruff.toml`; editor
settings in `.editorconfig`.

## Running the harness

```bash
export ANTHROPIC_API_KEY=...
urh submit examples/slug/spec.json     # prints a run id
urh run                                # drives every runnable run until done, failed or parked
urh status
urh parks                              # questions waiting for a person
urh answer <park_id> "approve"         # answers are claimed once, then the run is requeued
urh calls <run_id>                     # model-call log: tokens, cache hits, dollars
urh stats                              # park rate, human touches, cost and calls per verified run
urh trigger add-cron nightly "0 3 * * *" examples/slug/spec.json
URH_WEBHOOK_SECRET=... urh trigger add-webhook push examples/slug/spec.json
urh daemon --interval 5                # headless: fire triggers, wake parks, drive runs
URH_API_TOKEN=... urh serve --port 8787   # the same, plus the HTTP API (see src/urh/server.py)
```

Parks that need a person are pushed out as they happen: set `URH_NOTIFY_WEBHOOK` (with optional
`URH_NOTIFY_SECRET` and `URH_NOTIFY_FORMAT=slack`) or `URH_NOTIFY_FILE`. Delivery is at least once, with a
stable `Idempotency-Key` per park and channel.

A webhook POST to `/hooks/<name>` needs `X-URH-Signature: sha256=<HMAC of the body>`. GitHub's
`X-Hub-Signature-256` and `X-GitHub-Delivery` headers work as they are.

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
   breaker and park the run; that park wakes itself once the breaker closes. A budget shortfall tops up
   within a configured allowance before it parks.
6. The workspace is snapshotted to an unverified commit and the **gate** runs the spec's checks on a
   throwaway export with the hidden tests copied in. Changes to protected paths fail. No applicable check
   means `unsure`, which goes to a blind **judge** model (it sees the step and files, never the worker's
   own account of them).
7. **pass**: the commit is promoted (compare-and-swap on `refs/heads/verified`), the journal advances, and the
   step's held effects fire. **fail**: a bounded repair from the failed work; an attempt that reproduces a
   failed tree counts as a failure. When repairs run out, one attempt goes to the **escalation** model
   before the run parks. A park means a person is needed, so it is the failure mode `urh stats` tracks.

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

## Modules

| Module | Role |
| --- | --- |
| `journal.py` | SQLite (WAL) journal: runs, pins, leases, budget, attempts, verdicts, effects, parks, model calls |
| `checkpoint.py` | Per-run bare git repo, per-epoch workspaces, commit on gate pass, CAS promotion |
| `gateway.py` | Role-to-model pins, reservation, call log, retries and circuit breaker |
| `providers/` | Canonical request format and adapters: Anthropic, OpenAI-compatible |
| `pricing.py` | Per-model price book with overrides and a pessimistic fallback |
| `effects.py` | Effect guard and adapters (outbox file, webhook, unkeyed) |
| `gate.py` | Script gate and mutant-corpus audit |
| `judge.py` | Blind model judge for steps no script check covers |
| `stats.py` | Outcome metrics: park rate, human touches, cost and calls per verified run |
| `cron.py` | Five-field UTC cron expressions |
| `runtime.py` | Triggers (cron, signed webhooks) that fire exactly once, self-waking parks, bounded run pool |
| `notify.py` | Outbound park notifications (webhook, Slack-style, file) through a journaled outbox |
| `server.py` | HTTP API: runs, inbox, triggers, stats, `/hooks/<name>` (`urh serve`) |
| `worker.py` | Haiku 5.5 tool loop and confined workspace tools |
| `manager.py` | Code manager and Opus 5.5 manager |
| `context.py` | Stable prefix and per-step messages |
| `orchestrator.py` | The control loop: leases, verdict routing, repairs, parks, admission |
| `sandbox.py` | Scrubbed, timed, network-isolated command runner |
| `testing.py` | Scripted provider for deterministic tests and offline demos |

## Not built yet

Cue-triggered memory, cross-run rate limits beyond max active runs and a global spend cap, a mount-namespace
`/work` sandbox, call replay (D2), and the offline release loop. Postgres can replace SQLite when runs
span machines.
