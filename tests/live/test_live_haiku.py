"""Drives real Claude Haiku 5.5 workers through the harness. Costs a few cents.

Run with: ANTHROPIC_API_KEY=... python -m pytest -m live tests/live
"""

import os
import sys

import pytest

from urh.gateway import AnthropicProvider
from urh.orchestrator import Harness, HarnessConfig
from urh.spec import TaskSpec

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")),
                       reason="needs Anthropic credentials"),
]

EXAMPLE = os.path.join(os.path.dirname(__file__), "..", "..", "examples", "slug", "spec.json")


def test_haiku_worker_completes_slug_example(tmp_path):
    spec = TaskSpec.load(EXAMPLE)
    for check in spec.gate.checks:
        if check.cmd[0] == "python":
            check.cmd[0] = sys.executable
    h = Harness(str(tmp_path / "home"), AnthropicProvider(), config=HarnessConfig(worker_effort="low"))
    rid = h.submit(spec)
    status = h.run(rid)
    run = h.journal.get_run(rid)
    calls = h.journal.model_calls(rid)
    print(f"status={status} spent=${run.spent_usd:.4f} calls={len(calls)} "
          f"cache_read={sum(c['cache_read'] or 0 for c in calls)}")
    assert status == "done"
    assert all(c["model"] == "claude-haiku-5-5" for c in calls if c["role"] == "worker")
