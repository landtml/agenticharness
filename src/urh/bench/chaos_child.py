"""One harness process for the chaos bench. Separate module so the parent can SIGKILL it."""

from __future__ import annotations

import json
import sys
import time

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
        time.sleep(self.delay_s)
        return out


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
