import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from conftest import good_script, make_spec

from urh.notify import FileNotifier, WebhookNotifier, from_env
from urh.runtime import Runtime
from urh.signing import verify


class Flaky:
    name = "flaky"

    def __init__(self, fail_times):
        self.fail_times, self.sent = fail_times, []

    def send(self, key, message):
        if self.fail_times > 0:
            self.fail_times -= 1
            raise ConnectionError("down")
        self.sent.append((key, message))


class Later:
    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t


def parked_runtime(harness_factory, hidden, notifiers):
    h = harness_factory(good_script(), use_judge=False, escalate=False)
    spec = make_spec(hidden)
    spec.steps[1].checks = ["nonexistent"]
    rid = h.submit(spec)
    assert h.run(rid) == "parked"
    return Runtime(h, notifiers=notifiers), rid


def test_needed_park_is_notified_once_per_channel(harness_factory, hidden, tmp_path):
    f = FileNotifier(str(tmp_path / "n.jsonl"))
    rt, rid = parked_runtime(harness_factory, hidden, [f])
    try:
        assert len(rt.notify_parks()) == 1
        assert rt.notify_parks() == []  # already sent
        (line,) = (tmp_path / "n.jsonl").read_text().splitlines()
        msg = json.loads(line)
        assert msg["run_id"] == rid and msg["reason"] == "unsure" and msg["key"].endswith(":file")
    finally:
        rt.stop()


def test_failed_sends_retry_with_backoff_then_give_up(harness_factory, hidden):
    n = Flaky(fail_times=99)
    rt, _ = parked_runtime(harness_factory, hidden, [n])
    rt.notify_max_attempts = 3
    try:
        for _ in range(3):
            rt.notify_parks()
            rt.clock = Later(rt.clock() + 10_000)  # jump past the backoff
        (row,) = rt.journal.notifications()
        assert row["status"] == "failed" and row["attempts"] == 3 and "down" in row["last_error"]
    finally:
        rt.stop()


def test_a_send_that_recovers_is_delivered(harness_factory, hidden):
    n = Flaky(fail_times=1)
    rt, rid = parked_runtime(harness_factory, hidden, [n])
    try:
        assert rt.notify_parks() == []
        rt.clock = Later(rt.clock() + 60)
        assert len(rt.notify_parks()) == 1 and n.sent[0][1]["run_id"] == rid
    finally:
        rt.stop()


def test_self_waking_and_answered_parks_are_not_sent(harness_factory, hidden, tmp_path):
    f = FileNotifier(str(tmp_path / "n.jsonl"))
    script = good_script()
    script["fail_calls"] = 3
    h = harness_factory(script, outage_wake_s=3600)
    rid = h.submit(make_spec(hidden))
    assert h.run(rid) == "parked"  # outage: wakes itself
    rt = Runtime(h, notifiers=[f])
    try:
        assert rt.notify_parks() == [] and not (tmp_path / "n.jsonl").exists()
    finally:
        rt.stop()


def test_webhook_notifier_signs_and_sends_slack_text():
    got = {}

    class H(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            got["body"] = self.rfile.read(int(self.headers["content-length"]))
            got["headers"] = self.headers
            self.send_response(200)
            self.end_headers()

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.handle_request, daemon=True).start()
    n = WebhookNotifier(f"http://127.0.0.1:{srv.server_address[1]}/", secret="k" * 20, fmt="slack")
    n.send("p1:webhook", {"run_id": "r", "park_id": "p1", "reason": "unsure", "question": "ok?", "goal": "g"})
    srv.server_close()
    assert "needs a person" in json.loads(got["body"])["text"]
    assert got["headers"]["Idempotency-Key"] == "p1:webhook"
    assert verify("k" * 20, got["body"], got["headers"]["X-URH-Signature"])


def test_from_env():
    assert from_env({}) == []
    kinds = [
        type(n).__name__ for n in from_env({"URH_NOTIFY_WEBHOOK": "http://x", "URH_NOTIFY_FILE": "/tmp/x"})
    ]
    assert kinds == ["WebhookNotifier", "FileNotifier"]
