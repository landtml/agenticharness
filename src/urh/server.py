"""HTTP API for a headless harness: submit runs, read them, answer the inbox, manage triggers.

Everything under ``/v1`` needs ``Authorization: Bearer <token>``. A spec carries the gate's check
commands, so whoever can submit one can run code on this host: the token is that boundary.
``/hooks/<name>`` is the exception. It is authenticated by the trigger's HMAC signature instead, and
a hook can only start the trigger's fixed template with its body attached as untrusted input.

    GET    /healthz
    GET    /v1/runs                      POST /v1/runs {spec, budget_usd?, dedupe_key?}
    GET    /v1/runs/<id>                 GET  /v1/runs/<id>/events
    GET    /v1/inbox                     POST /v1/inbox/<park_id>/answer {text}
    GET    /v1/triggers                  POST /v1/triggers {name, kind, spec, schedule|secret, budget_usd?}
    POST   /v1/triggers/<name>/enable    POST /v1/triggers/<name>/disable
    DELETE /v1/triggers/<name>
    GET    /v1/sessions                  POST /v1/sessions {title, template, budget_usd?}
    GET    /v1/sessions/<id>             POST /v1/sessions/<id>/messages {text, checks?}
    GET    /v1/sessions/<id>/files
    GET    /v1/stats
    POST   /hooks/<name>                 (X-URH-Signature: sha256=<hmac>, X-URH-Delivery: <id>)
"""

from __future__ import annotations

import hmac
import json
import logging
import re
import signal
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from . import stats
from .runtime import Runtime, WebhookRejected
from .spec import TaskSpec

log = logging.getLogger("urh.server")

MAX_BODY = 1_000_000


class ApiError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


def _run_view(run: Any) -> dict[str, Any]:
    return {
        "id": run.id,
        "status": run.status,
        "goal": run.spec.get("goal"),
        "budget_usd": run.budget_usd,
        "spent_usd": round(run.spent_usd, 6),
        "status_reason": run.status_reason,
        "step_index": run.step_index,
        "verified_commit": run.verified_commit,
    }


def _trigger_view(t: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in t.items() if k not in ("secret", "spec")} | {"goal": t["spec"].get("goal")}


class Api:
    """Routing and handlers, independent of the HTTP plumbing so tests can call it directly."""

    def __init__(self, runtime: Runtime, token: str):
        if len(token) < 16:
            raise ValueError("API token must be at least 16 characters")
        self.rt = runtime
        self.j = runtime.journal
        self.token = token

    def handle(
        self, method: str, path: str, headers: dict[str, str], body: bytes
    ) -> tuple[int, dict[str, Any] | list[Any]]:
        try:
            if path == "/healthz":
                return 200, {"ok": True, "inflight": len(self.rt.inflight())}
            m = re.fullmatch(r"/hooks/([\w.-]+)", path)
            if m and method == "POST":
                return self._hook(m.group(1), headers, body)
            if not path.startswith("/v1/"):
                raise ApiError(404, "not found")
            auth = headers.get("authorization", "")
            if not hmac.compare_digest(auth.encode(), f"Bearer {self.token}".encode()):
                raise ApiError(401, "missing or bad bearer token")
            return self._v1(method, path[3:], self._json(body) if body else {})
        except ApiError as e:
            return e.status, {"error": str(e)}
        except WebhookRejected as e:
            return e.status, {"error": str(e)}
        except (KeyError, ValueError, TypeError) as e:
            return 400, {"error": f"{type(e).__name__}: {e}"}

    @staticmethod
    def _json(body: bytes) -> Any:
        try:
            return json.loads(body)
        except json.JSONDecodeError as e:
            raise ApiError(400, f"body is not JSON: {e}") from e

    def _hook(self, name: str, headers: dict[str, str], body: bytes) -> tuple[int, dict[str, Any]]:
        delivery = headers.get("x-urh-delivery") or headers.get("x-github-delivery")
        signature = headers.get("x-urh-signature") or headers.get("x-hub-signature-256")
        run_id, created = self.rt.fire_webhook(name, body, signature, delivery)
        return (201 if created else 200), {"run_id": run_id, "created": created}

    def _v1(self, method: str, path: str, data: Any) -> tuple[int, Any]:
        j = self.j
        if path == "/runs" and method == "GET":
            return 200, [_run_view(r) for r in j.list_runs()]
        if path == "/runs" and method == "POST":
            spec = TaskSpec.from_dict(data["spec"])
            dedupe = data.get("dedupe_key")
            existing = j.find_run_by_dedupe(dedupe) if dedupe else None
            run_id = self.rt.h.submit(spec, dedupe_key=dedupe, budget_usd=data.get("budget_usd"))
            return (200 if existing else 201), {"run_id": run_id, "created": existing is None}
        if m := re.fullmatch(r"/runs/(run_\w+)", path):
            if method != "GET":
                raise ApiError(405, "method not allowed")
            try:
                run = j.get_run(m.group(1))
            except KeyError as e:
                raise ApiError(404, "no such run") from e
            view = _run_view(run)
            view["parks"] = j.parks(run.id)
            view["attempts"] = [
                {k: a[k] for k in ("step_index", "attempt", "status")} for a in j.attempts(run.id)
            ]
            return 200, view
        if m := re.fullmatch(r"/runs/(run_\w+)/events", path):
            return 200, j.events(m.group(1))
        if path == "/inbox" and method == "GET":
            # what needs a person: open parks that will not wake themselves
            items = [p for p in j.parks(status="open") if p["preconditions"].get("wake_at") is None]
            return 200, [
                {k: p[k] for k in ("id", "run_id", "step_index", "reason", "question", "created_at")}
                for p in items
            ]
        if (m := re.fullmatch(r"/inbox/(\w+)/answer", path)) and method == "POST":
            text = str(data.get("text", "")).strip()
            if not text or text.startswith("auto:"):
                raise ApiError(400, "answer text is required and may not start with 'auto:'")
            try:
                run_id = j.answer_park(m.group(1), text)
            except ValueError as e:
                raise ApiError(409, str(e)) from e
            return 200, {"run_id": run_id, "requeued": True}
        if path == "/triggers" and method == "GET":
            return 200, [_trigger_view(t) for t in j.list_triggers()]
        if path == "/triggers" and method == "POST":
            spec = TaskSpec.from_dict(data["spec"])
            if data["kind"] == "cron":
                tid = self.rt.add_cron(data["name"], data["schedule"], spec, data.get("budget_usd"))
            elif data["kind"] == "webhook":
                tid = self.rt.add_webhook(data["name"], spec, data["secret"], data.get("budget_usd"))
            else:
                raise ApiError(400, "kind must be cron or webhook")
            return 201, _trigger_view(j.get_trigger(tid) or {})
        if m := re.fullmatch(r"/triggers/([\w.-]+)(?:/(enable|disable))?", path):
            name, action = m.group(1), m.group(2)
            try:
                if method == "DELETE" and action is None:
                    j.delete_trigger(name)
                    return 200, {"deleted": name}
                if method == "POST" and action:
                    j.set_trigger_enabled(name, action == "enable")
                    return 200, _trigger_view(j.get_trigger(name) or {})
            except KeyError as e:
                raise ApiError(404, "no such trigger") from e
            raise ApiError(405, "method not allowed")
        if path == "/sessions" and method == "GET":
            return 200, j.list_sessions()
        if path == "/sessions" and method == "POST":
            sid = self.rt.sessions.create(
                data["title"], data.get("template", {}), float(data.get("budget_usd", 1.0))
            )
            return 201, self.rt.sessions.view(sid)
        if m := re.fullmatch(r"/sessions/(ses_\w+)(/messages|/files)?", path):
            sid, sub = m.group(1), m.group(2)
            try:
                if sub == "/messages" and method == "POST":
                    seq = self.rt.sessions.send(sid, str(data.get("text", "")), data.get("checks"))
                    return 201, {"seq": seq, **self.rt.sessions.view(sid)}
                if sub == "/files" and method == "GET":
                    return 200, self.rt.sessions.files(sid)
                if sub is None and method == "GET":
                    return 200, self.rt.sessions.view(sid)
            except KeyError as e:
                raise ApiError(404, "no such session") from e
            raise ApiError(405, "method not allowed")
        if path == "/stats" and method == "GET":
            return 200, stats.compute(j)
        raise ApiError(404, "not found")


def make_server(api: Api, host: str = "127.0.0.1", port: int = 8787) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        server_version = "urh"

        def _serve(self, method: str) -> None:
            length = int(self.headers.get("content-length") or 0)
            if length > MAX_BODY:
                self._send(413, {"error": "body too large"})
                return
            body = self.rfile.read(length) if length else b""
            headers = {k.lower(): v for k, v in self.headers.items()}
            status, payload = api.handle(method, self.path.split("?", 1)[0], headers, body)
            self._send(status, payload)

        def _send(self, status: int, payload: Any) -> None:
            data = json.dumps(payload, default=str).encode()
            self.send_response(status)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self) -> None:  # noqa: N802
            self._serve("GET")

        def do_POST(self) -> None:  # noqa: N802
            self._serve("POST")

        def do_DELETE(self) -> None:  # noqa: N802
            self._serve("DELETE")

        def log_message(self, fmt: str, *args: Any) -> None:
            log.info("%s " + fmt, self.address_string(), *args)

    return ThreadingHTTPServer((host, port), Handler)


def serve(runtime: Runtime, token: str, host: str, port: int, interval: float = 1.0) -> None:
    """Run the API and the scheduler loop until interrupted."""
    httpd = make_server(Api(runtime, token), host, port)
    sched = threading.Thread(target=runtime.serve, args=(interval,), name="urh-scheduler", daemon=True)
    sched.start()
    log.info("urh serving on http://%s:%d", host, httpd.server_address[1])
    if threading.current_thread() is threading.main_thread():
        # service managers stop with SIGTERM: take the same clean path as Ctrl-C
        signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.shutdown()
        runtime.stop(wait=True)
