"""One harness process for the chaos bench. Separate module so the parent can SIGKILL it."""

from __future__ import annotations

import json
import os
import signal
import sys
import time

from .. import checkpoint, gate, journal
from ..effects import OutboxFileAdapter
from ..orchestrator import Harness, HarnessConfig
from ..testing import ScriptedProvider


class SlowOutbox(OutboxFileAdapter):
    """Widens the window between delivering an effect and journaling it, where a crash hurts most."""

    def __init__(self, directory: str, delay_s: float):
        super().__init__(directory)
        self.delay_s = delay_s

    def dispatch(self, key, payload, fence):
        out = super().dispatch(key, payload, fence)
        crash_once("effect_delivered")
        time.sleep(self.delay_s)
        return out


# Deterministic fault points: URH_FAULT names one, URH_FAULT_MARKER makes it fire only once.
FAULT = os.environ.get("URH_FAULT", "")
MARKER = os.environ.get("URH_FAULT_MARKER", "")


def crash_once(point: str) -> None:
    if FAULT == point and MARKER and not os.path.exists(MARKER):
        with open(MARKER, "w") as f:
            f.write(point)
        os.kill(os.getpid(), signal.SIGKILL)


def _wrap(cls, name: str, point: str, before: bool) -> None:
    original = getattr(cls, name)

    def wrapper(self, *a, **kw):
        if before:
            crash_once(point)
        out = original(self, *a, **kw)
        if not before:
            crash_once(point)
        return out

    setattr(cls, name, wrapper)


_wrap(checkpoint.GitCheckpoint, "promote", "before_promote", before=True)
_wrap(journal.Journal, "complete_step", "before_complete_step", before=True)
_wrap(journal.Journal, "complete_step", "after_complete_step", before=False)
_wrap(gate.ScriptGate, "evaluate", "after_gate", before=False)
_wrap(journal.Journal, "record_verdict", "after_verdict", before=False)


def main(argv: list[str]) -> int:
    home, script_path, run_id, lease_ttl, effect_delay = (
        argv[0],
        argv[1],
        argv[2],
        float(argv[3]),
        float(argv[4]),
    )
    with open(script_path) as f:
        script = json.load(f)
    cfg = HarnessConfig(lease_ttl=lease_ttl, heartbeat_s=lease_ttl / 4, provider_backoff_s=0.0)
    h = Harness(
        home, ScriptedProvider(script), adapters=[SlowOutbox(f"{home}/outbox", effect_delay)], config=cfg
    )
    print(h.run(run_id), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
