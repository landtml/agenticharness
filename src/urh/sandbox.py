"""Run commands for the worker and the gate with a scrubbed environment and no network.

Network isolation uses ``unshare --net --map-root-user`` when the kernel allows
it (probed once). Otherwise commands still run with a minimal environment and
a timeout, and :data:`NETWORK_ISOLATED` reports False so callers can refuse or
log it.
"""

from __future__ import annotations

import functools
import os
import shutil
import signal
import subprocess
import sys
from dataclasses import dataclass

_BASE_PATH = "/usr/local/bin:/usr/bin:/bin"


@functools.lru_cache(maxsize=1)
def network_isolation_available() -> bool:
    if os.environ.get("URH_NO_UNSHARE") == "1":
        return False
    exe = shutil.which("unshare")
    if not exe:
        return False
    try:
        r = subprocess.run([exe, "--net", "--map-root-user", "true"], capture_output=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return False
    return r.returncode == 0


@dataclass
class CommandResult:
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool


def scrubbed_env(home: str, extra: dict[str, str] | None = None) -> dict[str, str]:
    env = {
        "PATH": _BASE_PATH,
        "HOME": home,
        "LANG": "C.UTF-8",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONUNBUFFERED": "1",
        "TMPDIR": os.environ.get("TMPDIR", "/tmp"),
    }
    # Keep the interpreter that runs the harness reachable as `python3`, with its packages: a virtualenv's
    # bin directory, not the system interpreter its symlink resolves to, or `python3 -m pytest` finds no
    # pytest and every planner check and worker test run that uses it fails for a reason no step can fix.
    py_dir = os.path.dirname(os.path.abspath(sys.executable)) if sys.executable else ""
    if not py_dir or not os.path.exists(os.path.join(py_dir, "python3")):
        py_dir = os.path.dirname(os.path.realpath(shutil.which("python3") or "/usr/bin/python3"))
    if py_dir not in env["PATH"].split(":"):
        env["PATH"] = f"{py_dir}:{env['PATH']}"
    if extra:
        env.update(extra)
    return env


def run(
    cmd: list[str] | str,
    cwd: str,
    timeout: float = 60.0,
    network: bool = False,
    env: dict[str, str] | None = None,
    max_output: int = 200_000,
) -> CommandResult:
    shell = isinstance(cmd, str)
    argv: list[str] = ["/bin/bash", "-c", cmd] if shell else list(cmd)  # type: ignore[arg-type]
    if not network and network_isolation_available():
        argv = ["unshare", "--net", "--map-root-user", *argv]
    try:
        proc = subprocess.Popen(
            argv,
            cwd=cwd,
            env=env or scrubbed_env(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError as e:
        return CommandResult(127, "", f"cannot run command: {e.strerror}", False)
    try:
        out, err = proc.communicate(timeout=timeout)
        timed_out = False
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        out, err = proc.communicate()
        timed_out = True
    return CommandResult(
        returncode=proc.returncode if not timed_out else 124,
        stdout=out.decode(errors="replace")[:max_output],
        stderr=err.decode(errors="replace")[:max_output],
        timed_out=timed_out,
    )
