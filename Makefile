.PHONY: setup check py ts rs

VENV ?= .venv
PY := $(VENV)/bin

setup:
	python3 -m venv $(VENV)
	$(PY)/pip install -q -e '.[dev]'
	cd ts && npm install --no-audit --no-fund
	cd rust && cargo fetch

check: py ts rs

py:
	$(PY)/ruff check .
	$(PY)/ruff format --check .
	$(PY)/pytest -q || [ $$? -eq 5 ]

ts:
	cd ts && npm run check

rs:
	cd rust && cargo fmt --check && cargo clippy --all-targets -- -D warnings && cargo test
