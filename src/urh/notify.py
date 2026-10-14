"""Outbound notifications: a park that needs a person reaches them without anyone polling.

Delivery is at least once, and every message carries a stable ``Idempotency-Key``
(``<park_id>:<channel>``) so receivers can drop repeats. The journal's
``notifications`` table is the outbox: a row is written before the first send,
retried with backoff, and given up on after ``max_attempts``. A notification never
blocks a run.
"""

from __future__ import annotations

import json
import os
import urllib.request
from typing import Any, Protocol

from .signing import sign


class Notifier(Protocol):
    name: str

    def send(self, key: str, message: dict[str, Any]) -> None: ...


def render_text(m: dict[str, Any]) -> str:
    return (
        f"urh run {m['run_id']} needs a person ({m['reason']}): {m['question']}\n"
        f"Goal: {m.get('goal') or '-'}\n"
        f'Answer: urh answer {m["park_id"]} "..."  or  POST /v1/inbox/{m["park_id"]}/answer'
    )


class WebhookNotifier:
    """POST JSON to a URL. ``fmt="slack"`` sends ``{"text": ...}`` for Slack-style incoming webhooks."""

    def __init__(
        self,
        url: str,
        secret: str | None = None,
        fmt: str = "json",
        name: str = "webhook",
        timeout: float = 10.0,
    ):
        if fmt not in ("json", "slack"):
            raise ValueError("fmt must be json or slack")
        self.url, self.secret, self.fmt, self.name, self.timeout = url, secret, fmt, name, timeout

    def send(self, key: str, message: dict[str, Any]) -> None:
        body = json.dumps({"text": render_text(message)} if self.fmt == "slack" else message).encode()
        headers = {"Content-Type": "application/json", "Idempotency-Key": key}
        if self.secret:
            headers["X-URH-Signature"] = sign(self.secret, body)
        req = urllib.request.Request(self.url, data=body, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:  # noqa: S310 (operator-configured URL)
            if resp.status >= 300:
                raise RuntimeError(f"notifier got HTTP {resp.status}")


class FileNotifier:
    """Append one JSON line per notification (local setups, tests, or a log shipper)."""

    def __init__(self, path: str, name: str = "file"):
        self.path, self.name = path, name

    def send(self, key: str, message: dict[str, Any]) -> None:
        os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
        with open(self.path, "a") as f:
            f.write(json.dumps({"key": key, **message}, sort_keys=True) + "\n")


def from_env(env: dict[str, str] | None = None) -> list[Notifier]:
    env = dict(os.environ if env is None else env)
    out: list[Notifier] = []
    if env.get("URH_NOTIFY_WEBHOOK"):
        out.append(
            WebhookNotifier(
                env["URH_NOTIFY_WEBHOOK"], env.get("URH_NOTIFY_SECRET"), env.get("URH_NOTIFY_FORMAT", "json")
            )
        )
    if env.get("URH_NOTIFY_FILE"):
        out.append(FileNotifier(env["URH_NOTIFY_FILE"]))
    return out
