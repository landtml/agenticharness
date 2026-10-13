import os
import sys

import pytest

from urh.orchestrator import Harness, HarnessConfig
from urh.spec import TaskSpec
from urh.testing import ScriptedProvider

PY = sys.executable

ADD_PY = "def add(a, b):\n    return a + b\n"
MUL_PY = "def mul(a, b):\n    return a * b\n"


@pytest.fixture
def hidden(tmp_path):
    """Hidden tests the worker never sees."""
    d = tmp_path / "hidden"
    d.mkdir()
    (d / "test_add.py").write_text("from add import add\n\ndef test_add():\n    assert add(2, 3) == 5\n")
    (d / "test_mul.py").write_text("from mul import mul\n\ndef test_mul():\n    assert mul(2, 3) == 6\n")
    return str(d)


def make_spec(hidden: str, **over) -> TaskSpec:
    d = {
        "goal": "Write a tiny arithmetic library",
        "constraints": ["Standard library only"],
        "gate": {
            "hidden_dir": hidden,
            "checks": [
                {"name": "add", "cmd": [PY, "-m", "pytest", "-q", "-p", "no:cacheprovider", "_hidden/test_add.py"]},
                {"name": "mul", "cmd": [PY, "-m", "pytest", "-q", "-p", "no:cacheprovider", "_hidden/test_mul.py"]},
            ],
            "protected": ["_hidden/"],
        },
        "steps": [
            {"title": "add", "instructions": "Write add.py with add(a, b).", "files": ["add.py"], "checks": ["add"]},
            {"title": "mul", "instructions": "Write mul.py with mul(a, b).", "files": ["mul.py"], "checks": ["add", "mul"]},
        ],
        "budget_usd": 0.5,
    }
    d.update(over)
    return TaskSpec.from_dict(d)


def good_script(**extra_steps):
    steps = {
        "1": [[{"write": "add.py", "content": ADD_PY}, {"effect": "outbox_file", "payload": {"msg": "add ready"}}],
              [{"finish": "add written"}]],
        "2": [[{"write": "mul.py", "content": MUL_PY}], [{"finish": "mul written"}]],
    }
    steps.update(extra_steps)
    return {"steps": steps}


def fast_config(**over) -> HarnessConfig:
    cfg = HarnessConfig(lease_ttl=30, heartbeat_s=5, provider_retries=2, provider_backoff_s=0.0)
    for k, v in over.items():
        setattr(cfg, k, v)
    return cfg


@pytest.fixture
def harness_factory(tmp_path):
    def make(script, home=None, **cfg):
        return Harness(str(home or tmp_path / "home"), ScriptedProvider(script), config=fast_config(**cfg))
    return make


def deliveries(home) -> list[str]:
    path = os.path.join(str(home), "outbox", "deliveries.log")
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return f.read().split()
