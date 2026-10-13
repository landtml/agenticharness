# Working in this repo

This file is read by every Claude session and agent that works here, including the
Haiku 5.5 workers the harness drives.

## Ground rules

- Models: Opus is the manager/judge, Claude Haiku 5.5 does worker steps. Reach models
  only through Anthropic (SDK or `claude` CLI). Never add OpenRouter or other providers.
- Durability first: any state that must outlive a crash goes to the journal before
  the run moves on. Test resume with a real `SIGKILL`, not a mock.
- Effects: every outward write carries an idempotency key attached by the effect
  guard; a write with no key and no read-back is parked, not retried.
- Gates read artifacts, never a worker's self-report, and workers cannot write to them.
- Keep modules small and replaceable; delete what does not pay for itself.

## Commands

- `make check` runs everything CI runs. Run it before every push.
- Python: `ruff check . && ruff format --check . && pytest`
- TypeScript: `cd ts && npm run check`
- Rust: `cd rust && cargo fmt --check && cargo clippy -- -D warnings && cargo test`
- Tests that call real models are marked `live` (pytest `-m live`) and need credentials.

## Conventions

- Python >= 3.11, `src/` layout, ruff for lint and format, line length 110.
- TypeScript strict mode, ESM, Node 22.
- Rust 2021 edition, workspace under `rust/`.
- Branch per change, PR into `main`, CI green before merge.
