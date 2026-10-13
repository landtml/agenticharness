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
| `.github/workflows/` | CI: ruff and pytest on every push to `main` and every pull request |

TypeScript or Rust components, if added, go in their own top-level folders with their own toolchain config.

## Development

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e '.[dev]'
ruff check .
python -m pytest -q                 # offline tests
python -m pytest -m live tests/live # needs ANTHROPIC_API_KEY
```

Python 3.11 or newer (CI uses 3.12). Lint settings are in `ruff.toml`; editor settings in `.editorconfig`.
