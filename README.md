# agenticharness

The Upper-Right Harness (URH): a durable, headless agent orchestrator. A Claude Opus 5.5 manager plans work,
Claude Haiku 5.5 workers do it (build, code, test, lint, scout, scaffold), script gates decide when work is
done, and a journal lets any run survive `kill -9` without redoing verified steps. Models are reached only
through the Anthropic API.

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
