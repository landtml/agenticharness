import json
import threading
import urllib.request

import pytest
from conftest import good_script, make_spec

from urh.runtime import Runtime
from urh.server import Api, make_server
from urh.signing import sign

TOKEN = "t" * 24
AUTH = {"authorization": f"Bearer {TOKEN}"}


@pytest.fixture
def api(harness_factory):
    rt = Runtime(harness_factory(good_script(), max_active_runs=2))
    yield Api(rt, TOKEN)
    rt.stop()


def call(api, method, path, body=None, headers=AUTH):
    raw = json.dumps(body).encode() if body is not None else b""
    return api.handle(method, path, dict(headers), raw)


def test_v1_needs_the_bearer_token(api):
    assert call(api, "GET", "/v1/runs", headers={})[0] == 401
    assert call(api, "GET", "/v1/runs", headers={"authorization": "Bearer wrong"})[0] == 401
    assert call(api, "GET", "/healthz", headers={})[0] == 200


def test_submit_run_dedupes_and_finishes_headless(api, hidden):
    spec = make_spec(hidden).to_dict()
    status, body = call(api, "POST", "/v1/runs", {"spec": spec, "dedupe_key": "job-1"})
    assert status == 201 and body["created"]
    status, again = call(api, "POST", "/v1/runs", {"spec": spec, "dedupe_key": "job-1"})
    assert status == 200 and again["run_id"] == body["run_id"] and not again["created"]
    api.rt.dispatch()
    assert api.rt.wait_idle()
    status, run = call(api, "GET", f"/v1/runs/{body['run_id']}")
    assert run["status"] == "done" and run["parks"] == []
    assert call(api, "GET", "/v1/stats")[1]["headless_done"] == 1


def test_inbox_lists_only_parks_that_need_a_person_and_takes_answers(api, hidden):
    spec = make_spec(hidden)
    spec.steps[1].checks = ["nonexistent"]
    api.rt.h.config.use_judge = False
    rid = api.rt.h.submit(spec)
    assert api.rt.h.run(rid) == "parked"
    _, inbox = call(api, "GET", "/v1/inbox")
    assert [p["run_id"] for p in inbox] == [rid]
    pid = inbox[0]["id"]
    assert call(api, "POST", f"/v1/inbox/{pid}/answer", {"text": "auto: sneaky"})[0] == 400
    assert call(api, "POST", f"/v1/inbox/{pid}/answer", {"text": "looks right, ship it"})[0] == 200
    assert call(api, "POST", f"/v1/inbox/{pid}/answer", {"text": "twice"})[0] == 409
    assert call(api, "GET", "/v1/inbox")[1] == []


def test_triggers_over_http_and_webhook_over_a_real_socket(api, hidden):
    spec = make_spec(hidden).to_dict()
    bad = {"name": "h", "kind": "webhook", "spec": spec, "secret": "short"}
    assert call(api, "POST", "/v1/triggers", bad)[0] == 400
    status, trig = call(api, "POST", "/v1/triggers", {**bad, "secret": "x" * 20})
    assert status == 201 and "secret" not in trig
    assert (
        call(api, "POST", "/v1/triggers", {"name": "c", "kind": "cron", "schedule": "@daily", "spec": spec})[
            0
        ]
        == 201
    )
    assert {t["name"] for t in call(api, "GET", "/v1/triggers")[1]} == {"h", "c"}

    httpd = make_server(api, "127.0.0.1", 0)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        body = b'{"ref": "main"}'
        req = urllib.request.Request(
            f"http://127.0.0.1:{httpd.server_address[1]}/hooks/h",
            data=body,
            method="POST",
            headers={"X-URH-Signature": sign("x" * 20, body), "X-URH-Delivery": "abc"},
        )
        with urllib.request.urlopen(req) as resp:
            assert resp.status == 201
            assert json.load(resp)["created"] is True
    finally:
        httpd.shutdown()
    assert call(api, "POST", "/v1/triggers/h/disable")[1]["enabled"] is False
    assert call(api, "DELETE", "/v1/triggers/c")[0] == 200
    assert call(api, "DELETE", "/v1/triggers/c")[0] == 404
