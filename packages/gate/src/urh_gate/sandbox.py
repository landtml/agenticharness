"""Parent side of the sandbox: launch the runner, enforce limits, parse its report."""

import os
import secrets
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field

from . import values

RUNNER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "runner.py")
MAGIC = b"URHGATE1"


@dataclass
class RunReport:
    ok: bool  # a single well-formed frame came back
    problem: str = ""  # why not, when ok is False
    import_status: str = ""
    calls: list = field(default_factory=list)
    violations: list = field(default_factory=list)


def call(fn, *args):
    """One call in a program: the args are tagged values."""
    return {"fn": fn, "args": [values.encode(a) for a in args]}


def ref(index):
    """An argument that is the return value of an earlier call in the program."""
    return ["ref", index]


def run_program(
    source,
    program,
    *,
    per_call_timeout=2.0,
    wall_timeout=None,
    hash_seed=0,
    mem_bytes=1 << 30,
    cpu_seconds=None,
    filename="solution.py",
):
    """Run ``program`` against candidate ``source`` in a fresh child process."""
    nonce = secrets.token_hex(16)
    if cpu_seconds is None:
        cpu_seconds = int(min(240, 20 + 0.05 * len(program)))
    req = {
        "nonce": nonce,
        "source": source,
        "filename": filename,
        "program": program,
        "per_call_timeout": per_call_timeout,
        "mem_bytes": mem_bytes,
        "cpu_seconds": cpu_seconds,
    }
    if wall_timeout is None:
        wall_timeout = 10.0 + per_call_timeout * max(1, len(program)) * 0.5
        wall_timeout = min(wall_timeout, 300.0)
    import json

    payload = json.dumps(req).encode()
    with tempfile.TemporaryDirectory(prefix="urh-gate-") as cwd:
        env = {
            "PATH": "/usr/bin:/bin",
            "HOME": cwd,
            "LANG": "C.UTF-8",
            "PYTHONHASHSEED": str(hash_seed),
            "PYTHONDONTWRITEBYTECODE": "1",
        }
        try:
            proc = subprocess.run(
                # Not -I: it implies -E, which would discard PYTHONHASHSEED. The
                # environment is fully controlled above, so -E buys nothing, and
                # without -I the interpreter's flags look like a normal run.
                [sys.executable, "-s", "-S", "-B", RUNNER],
                input=payload,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                cwd=cwd,
                env=env,
                timeout=wall_timeout,
                start_new_session=True,
            )
        except subprocess.TimeoutExpired:
            return RunReport(ok=False, problem="wall-clock timeout")
    return parse_frame(proc.stdout, nonce)


def parse_frame(data, nonce):
    header, sep, body = data.partition(b"\n")
    if not sep:
        return RunReport(ok=False, problem="no report (process exited early)")
    parts = header.split(b" ")
    if len(parts) != 3 or parts[0] != MAGIC:
        return RunReport(ok=False, problem="malformed report header")
    if parts[1].decode(errors="replace") != nonce:
        return RunReport(ok=False, problem="report nonce mismatch")
    try:
        length = int(parts[2])
    except ValueError:
        return RunReport(ok=False, problem="malformed report length")
    if len(body) != length:
        # Either truncated or the candidate wrote extra bytes to the channel.
        return RunReport(ok=False, problem="report channel tampered or truncated")
    import json

    try:
        msg = json.loads(body)
    except ValueError:
        return RunReport(ok=False, problem="report not JSON")
    if msg.get("nonce") != nonce:
        return RunReport(ok=False, problem="report nonce mismatch")
    return RunReport(
        ok=True,
        import_status=msg.get("import") or "",
        calls=msg.get("calls") or [],
        violations=msg.get("violations") or [],
    )
