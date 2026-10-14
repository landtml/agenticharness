"""Run commands for the worker and the gate in a jail: no network, and no filesystem but ``/work``.

Where the kernel allows unprivileged user and mount namespaces (probed once), every command runs as:

- a new user, mount, PID and network namespace (``unshare --map-root-user``);
- a new root that is the host filesystem bind-mounted **read-only**, with empty tmpfs over the places
  that hold anyone's data (``/home``, ``/root``, ``/tmp``, ``/mnt``, ``/srv``, ``/var/tmp``, ``/run``);
- the Python interpreter and its site-packages bound back read-only, so ``python`` and ``pytest`` work
  even from a virtualenv under ``/home`` (more paths: ``URH_SANDBOX_RO``, colon-separated);
- the command's own folder bound read-write at ``/work``, which is its cwd and ``$HOME``;
- a fresh ``/proc`` for the new PID namespace, so ``/proc/<pid>/cwd`` of a host process is unreachable.

So ``cd /`` works but finds nothing to read or write: not the journal, the run repos, the gate's
hidden tests or the source tree. Without namespaces, commands still get a scrubbed environment and a
timeout, and :func:`jail_available` reports False so the caller can refuse (``URH_SANDBOX=require``).
"""

from __future__ import annotations

import functools
import os
import shutil
import signal
import site
import subprocess
import sys
import tempfile
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


HIDDEN_DIRS = ("/home", "/root", "/tmp", "/mnt", "/srv", "/var/tmp", "/run", "/media")

# Runs inside the new namespaces as root of the user namespace. $1 = new root (an empty dir), $2 = the
# workspace, $3 = newline-separated read-only re-exposures, $4 = more dirs to hide; the rest is the command. The new root is a
# tmpfs holding read-only binds of the host's top-level dirs, so nothing is created on the host.
_JAIL = r"""
set -e
R="$1"; WS="$2"; RO="$3"; HIDE="$4"; shift 4
P0="$PATH"; PATH=/usr/sbin:/usr/bin:/sbin:/bin
mount -t tmpfs -o size=64m,mode=755 urh-root "$R"
for e in /* /.[!.]*; do
    [ -e "$e" ] || [ -L "$e" ] || continue
    n="${e#/}"
    case " @HIDDEN@ /proc /work " in *" $e "*) mkdir -p "$R$e"; continue;; esac
    if [ -L "$e" ]; then cp -P "$e" "$R/$n"
    elif [ -d "$e" ]; then mkdir "$R/$n"; mount --rbind "$e" "$R/$n" 2>/dev/null || rmdir "$R/$n"
    fi
done
for d in @HIDDEN@ /proc /work; do mkdir -p "$R$d"; done
for m in $(awk '{print $5}' /proc/self/mountinfo | grep "^$R/" | sort -r); do
    case "$m" in "$R/dev"*) continue;; esac
    mount -o remount,bind,ro "$m" 2>/dev/null || true
done
for d in @HIDDEN@; do
    mount -t tmpfs -o size=256m,mode=1777 tmpfs "$R$d"
done
printf '%s\n' "$RO" | while IFS= read -r p; do
    [ -n "$p" ] && [ -e "$p" ] || continue
    mkdir -p "$R$p"
    mount --rbind "$p" "$R$p" && mount -o remount,bind,ro "$R$p" 2>/dev/null || true
done
printf '%s\n' "$HIDE" | while IFS= read -r p; do
    [ -n "$p" ] && [ -d "$R$p" ] && mount -t tmpfs -o size=1m,mode=555 tmpfs "$R$p" || true
done
mount --bind "$WS" "$R/work"
for d in @HIDDEN@; do
    [ "$d" = /tmp ] || mount -o remount,ro "$R$d" 2>/dev/null || true
done
mount -o remount,ro "$R"
CHROOT=$(command -v chroot); PATH="$P0"
exec "$CHROOT" "$R" /bin/sh -c 'mount -t proc proc /proc 2>/dev/null || true; cd /work && exec "$@"' urh-jail "$@"
""".replace("@HIDDEN@", " ".join(HIDDEN_DIRS))


_HIDE: set[str] = set()


def hide(path: str) -> None:
    """Hide ``path`` from every jailed command, e.g. a harness home outside the dirs hidden by default."""
    _HIDE.add(os.path.realpath(path))


def _hide_paths() -> list[str]:
    extra = {os.path.realpath(p) for p in os.environ.get("URH_SANDBOX_HIDE", "").split(":") if p}
    return sorted(p for p in _HIDE | extra if p != "/")


def _ro_paths() -> list[str]:
    paths = {sys.prefix, sys.base_prefix, sys.exec_prefix, os.path.dirname(os.path.realpath(sys.executable))}
    try:
        paths.update(site.getsitepackages())
        paths.add(site.getusersitepackages())
    except AttributeError:  # pragma: no cover - some embedded interpreters lack these
        pass
    paths.update(p for p in os.environ.get("URH_SANDBOX_RO", "").split(":") if p)
    hidden = tuple(d + "/" for d in HIDDEN_DIRS)
    return sorted(p for p in paths if os.path.exists(p) and (p + "/").startswith(hidden))


@functools.lru_cache(maxsize=1)
def jail_available() -> bool:
    if os.environ.get("URH_NO_UNSHARE") == "1" or not shutil.which("unshare") or not shutil.which("chroot"):
        return False
    with tempfile.TemporaryDirectory(prefix="urh-probe-") as ws:
        r = _jailed(["/bin/sh", "-c", "test -d /work && ! test -e /work/../tmp/urh-probe-marker"], ws, 20)
    return r is not None and r.returncode == 0


def _jailed(argv: list[str], workspace: str, timeout: float) -> subprocess.CompletedProcess[bytes] | None:
    root = tempfile.mkdtemp(prefix="urh-jail-")
    try:
        return subprocess.run(
            _jail_argv(argv, workspace, root), capture_output=True, timeout=timeout, stdin=subprocess.DEVNULL
        )
    except (OSError, subprocess.SubprocessError):
        return None
    finally:
        os.rmdir(root)


def _jail_argv(argv: list[str], workspace: str, root: str) -> list[str]:
    return [
        "unshare", "--user", "--map-root-user", "--mount", "--pid", "--fork", "--net", "--propagation", "private",
        "/bin/sh", "-c", _JAIL, "urh-jail", root, os.path.realpath(workspace), "\n".join(_ro_paths()), "\n".join(_hide_paths()), *argv,
    ]  # fmt: skip


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
    # Keep the interpreter that runs the harness reachable as `python`, unresolved: a virtualenv's bin/python
    # is a symlink, and resolving it would lose the venv's packages.
    py_dir = os.path.dirname(sys.executable) if sys.executable else ""
    if not py_dir:
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
    env = dict(env or scrubbed_env(cwd))
    root = None
    if not network and jail_available():
        root = tempfile.mkdtemp(prefix="urh-jail-")
        argv = _jail_argv(argv, cwd, root)
        env.update(HOME="/work", TMPDIR="/tmp")
    elif os.environ.get("URH_SANDBOX") == "require":
        return CommandResult(126, "", "sandbox required but this host has no user/mount namespaces", False)
    elif not network and network_isolation_available():
        argv = ["unshare", "--net", "--map-root-user", *argv]
    try:
        return _spawn(argv, cwd, env, timeout, max_output)
    finally:
        if root is not None:
            os.rmdir(root)


def _spawn(argv: list[str], cwd: str, env: dict[str, str], timeout: float, max_output: int) -> CommandResult:
    try:
        proc = subprocess.Popen(
            argv,
            cwd=cwd,
            env=env,
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
