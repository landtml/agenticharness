"""Sandboxed runner: executes one candidate program and reports raw outputs.

Run only as a child process by ``sandbox.py`` (``python -s -S -B runner.py``).
The runner never sees expected values. It calls the candidate on the inputs
it is given and reports what came back; the parent decides the verdict. A
candidate that tampers with this process can therefore only change its own
reported outputs, which are exactly what it is judged on, plus the side
signals (mutation, violations); those are protected by the layers below.

Layers, in order of installation:
  1. stdout/stderr point at /dev/null; the report goes out on a private dup of
     the original stdout, as exactly one framed message. Extra bytes on that
     pipe are a protocol violation and fail the candidate.
  2. Resource limits: address space, CPU seconds, no file creation.
  3. Dangerous modules are hidden from ``sys.modules`` so importing them again
     raises an audit event.
  4. An audit hook (which cannot be removed) denies file opens, process
     creation, sockets, ctypes, fresh imports, frame walking and gc
     introspection, and records every denial so a swallowed exception still
     counts against the candidate.
  5. The runner's own logic uses only references bound before the candidate
     loads, a private serializer (no ``json``) and exact ``type()`` checks
     (no ``isinstance``, which a spoofed ``__class__`` can fool). The builtins
     module is fingerprinted before the candidate runs and checked after
     every call; a change is a violation and is reverted.
  6. Each call runs under an interval timer; the parent also enforces a
     wall-clock timeout and kills the process.
"""

import os
import sys

# Private references taken before any candidate code exists.
_write = os.write
_exit = os._exit
_dup = os.dup
_dup2 = os.dup2
_open_fd = os.open
_devnull = os.devnull
_O_RDWR = os.O_RDWR

import builtins  # noqa: E402
import copy  # noqa: E402
import json  # noqa: E402
import resource  # noqa: E402
import signal  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import values  # noqa: E402

_encode = values.encode
_decode = values.decode
_EncodeError = values.EncodeError
_ValueError = ValueError
_BaseException = BaseException
_deepcopy = copy.deepcopy
_loads = json.loads
_setitimer = signal.setitimer
_ITIMER_REAL = signal.ITIMER_REAL
_type = type
_issubclass = issubclass
_len = len
_str = str
_int = int
_float = float
_repr = repr
_ord = ord
_id = id
_callable = callable
_list = list
_dict = dict
_bool = bool
_NoneType = type(None)
_builtins_dict = builtins.__dict__

FRAME_MAGIC = b"URHGATE1"

# Modules a pure-function candidate may import. They are loaded before the
# audit hook so importing them is a cache hit and raises no event.
SAFE_MODULES = (
    "re",
    "string",
    "math",
    "cmath",
    "collections",
    "collections.abc",
    "itertools",
    "functools",
    "operator",
    "bisect",
    "heapq",
    "typing",
    "dataclasses",
    "enum",
    "fractions",
    "decimal",
    "numbers",
    "textwrap",
    "unicodedata",
    "array",
    "abc",
    "types",
    "copy",
    "posixpath",
    "statistics",
    "json",
    "keyword",
    "reprlib",
    "contextlib",
    "weakref",
)

# Loaded by the runner itself but hidden from the candidate.
HIDDEN_MODULES = (
    "signal",
    "_signal",
    "resource",
    "values",
    "gc",
    "ctypes",
    "_ctypes",
    "subprocess",
    "socket",
    "_socket",
    "_posixsubprocess",
    "threading",
    "_thread",
    "multiprocessing",
    "inspect",
    "importlib",
    "marshal",
    "pickle",
    "_pickle",
    "shutil",
    "tempfile",
    "io",
    "_io",
)

DENY_EXACT = {
    "open",
    "os.system",
    "os.exec",
    "os.posix_spawn",
    "os.spawn",
    "os.fork",
    "os.forkpty",
    "os.kill",
    "os.killpg",
    "os.remove",
    "os.rename",
    "os.rmdir",
    "os.mkdir",
    "os.chmod",
    "os.chown",
    "os.truncate",
    "os.symlink",
    "os.link",
    "os.chdir",
    "os.putenv",
    "os.unsetenv",
    "os.listdir",
    "os.scandir",
    "os.walk",
    "os.startfile",
    "os.utime",
    "subprocess.Popen",
    "pty.spawn",
    "import",
    "sys._getframe",
    "sys._current_frames",
    "sys.setprofile",
    "sys.settrace",
    "sys._getframemodulename",
    "compile",
    "exec",
    "builtins.input",
    "code.__new__",
    "function.__new__",
    "object.__getattr__",
    "object.__setattr__",
    "object.__delattr__",
    "gc.get_objects",
    "gc.get_referrers",
    "gc.get_referents",
    "mmap.__new__",
    "fcntl.fcntl",
    "fcntl.ioctl",
    "resource.setrlimit",
    "signal.pthread_kill",
    "glob.glob",
    "shutil.rmtree",
    "shutil.copyfile",
    "sys.addaudithook",
    "cpython.run_command",
    "urllib.Request",
    "webbrowser.open",
    "os.add_dll_directory",
}
DENY_PREFIX = (
    "socket.",
    "ctypes.",
    "subprocess.",
    "shutil.",
    "os.exec",
    "os.spawn",
    "os.posix_spawn",
    "winreg.",
    "msvcrt.",
    "_winapi.",
    "sqlite3.",
    "ftplib.",
    "smtplib.",
    "http.",
    "telnetlib.",
    "nntplib.",
    "poplib.",
    "imaplib.",
)


class _Timeout(BaseException):
    pass


_violations = []
_hook_armed = [False]
_own_exec = [False]  # lets the runner's single exec of the candidate through


def _note(detail):
    if _len(_violations) < 20:
        _violations.append(detail)


def _audit(event, args):
    if not _hook_armed[0]:
        return
    if event == "exec" and _own_exec[0]:
        _own_exec[0] = False
        return
    if event in DENY_EXACT or event.startswith(DENY_PREFIX):
        detail = event
        if event == "import" and args:
            detail = "import " + _str(args[0])
        elif event == "open" and args:
            detail = "open " + _str(args[0])[:80]
        _note(detail)
        raise RuntimeError("blocked by gate sandbox: " + event)


def _on_alarm(signum, frame):
    raise _Timeout()


# ----------------------------------------------------------- private JSON out
def _json_str(s):
    out = ['"']
    for ch in s:
        o = _ord(ch)
        if ch == '"':
            out.append('\\"')
        elif ch == "\\":
            out.append("\\\\")
        elif 0x20 <= o < 0x7F:
            out.append(ch)
        elif o < 0x10000:
            out.append(f"\\u{o:04x}")
        else:
            o -= 0x10000
            out.append(f"\\u{0xD800 + (o >> 10):04x}\\u{0xDC00 + (o & 0x3FF):04x}")
    out.append('"')
    return "".join(out)


def _json(v):
    t = _type(v)
    if v is None:
        return "null"
    if t is _bool:
        return "true" if v else "false"
    if t is _int:
        return _str(v)
    if t is _str:
        return _json_str(v)
    if t is _list:
        return "[" + ",".join([_json(x) for x in v]) + "]"
    if t is _dict:
        return "{" + ",".join([_json_str(k) + ":" + _json(x) for k, x in v.items()]) + "}"
    raise TypeError("unserializable")


def _send(fd, payload):
    body = _json(payload).encode("ascii")
    header = FRAME_MAGIC + b" " + payload["nonce"].encode() + b" " + _str(_len(body)).encode() + b"\n"
    data = header + body
    while data:
        n = _write(fd, data)
        data = data[n:]


# ------------------------------------------------------------ integrity
def _fingerprint():
    return {k: _id(v) for k, v in _builtins_dict.items()}


def _check_builtins(reference, originals):
    changed = False
    for k in _list(_builtins_dict.keys()):
        if k not in reference:
            changed = True
            del _builtins_dict[k]
    for k, ident in reference.items():
        if k not in _builtins_dict or _id(_builtins_dict[k]) != ident:
            changed = True
            _builtins_dict[k] = originals[k]
    if changed:
        _note("builtins modified")
    return changed


def _resolve(arg, results):
    if arg[0] == "ref":
        r = results[arg[1]]
        if "ok" not in r:
            raise LookupError("referenced call did not return a value")
        return _decode(r["ok"])
    return _decode(arg)


def _safe_encode(v):
    try:
        return _encode(v)
    except _BaseException:
        return None


def main():
    raw = sys.stdin.buffer.read()
    req = _loads(raw.decode())
    nonce = req["nonce"]

    # 1. Private report channel, silence the candidate's stdio.
    report_fd = _dup(1)
    null_fd = _open_fd(_devnull, _O_RDWR)
    _dup2(null_fd, 0)
    _dup2(null_fd, 1)
    _dup2(null_fd, 2)

    # 2. Resource limits.
    mem = _int(req.get("mem_bytes", 1 << 30))
    try:
        resource.setrlimit(resource.RLIMIT_AS, (mem, mem))
    except (ValueError, OSError):
        pass
    cpu = _int(req.get("cpu_seconds", 20))
    resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu + 1))
    resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))

    for name in SAFE_MODULES:
        try:
            __import__(name)
        except ImportError:
            pass

    code = compile(req["source"], "/work/" + req.get("filename", "solution.py"), "exec")

    signal.signal(signal.SIGALRM, _on_alarm)
    sys.setrecursionlimit(_int(req.get("recursion_limit", 5000)))

    # 3. Hide modules the candidate has no business with.
    for name in HIDDEN_MODULES:
        sys.modules.pop(name, None)
    sys.modules.pop("__main__", None)

    # 4. Audit hook, armed from here on.
    sys.addaudithook(_audit)

    originals = _dict(_builtins_dict)
    reference = _fingerprint()
    module_globals = {"__name__": "solution", "__file__": "/work/solution.py", "__builtins__": builtins}
    out = {"nonce": nonce, "import": None, "calls": [], "violations": _violations}
    per_call = _float(req.get("per_call_timeout", 2.0))

    _own_exec[0] = True
    _hook_armed[0] = True
    try:
        _setitimer(_ITIMER_REAL, _float(req.get("import_timeout", 5.0)))
        try:
            exec(code, module_globals)
        finally:
            _setitimer(_ITIMER_REAL, 0)
        out["import"] = "ok"
    except _Timeout:
        out["import"] = "timeout"
    except _BaseException as e:  # SystemExit and KeyboardInterrupt included
        out["import"] = "error:" + _type(e).__name__
    _check_builtins(reference, originals)

    results = out["calls"]
    if out["import"] == "ok":
        stop = False
        for call in req["program"]:
            if stop:
                results.append({"skipped": True})
                continue
            fn = module_globals.get(call["fn"])
            if not _callable(fn):
                results.append({"missing": call["fn"]})
                continue
            try:
                args = [_resolve(a, results) for a in call["args"]]
            except LookupError:
                results.append({"skipped": True})
                continue
            before = _safe_encode(args)
            entry = {}
            try:
                _setitimer(_ITIMER_REAL, per_call)
                try:
                    value = fn(*args)
                finally:
                    _setitimer(_ITIMER_REAL, 0)
                # Restore builtins before our own code touches the result.
                if _check_builtins(reference, originals):
                    entry["builtins"] = True
                try:
                    entry["ok"] = _encode(value)
                except _EncodeError as e:
                    entry["bad"] = _str(e)
                except _Timeout:
                    raise
                except _BaseException as e:
                    entry["bad"] = "encode failed: " + _type(e).__name__
            except _Timeout:
                entry["timeout"] = True
                stop = True
            except _BaseException as e:
                if _check_builtins(reference, originals):
                    entry["builtins"] = True
                cls = _type(e)  # the real class; a spoofed __class__ is ignored
                entry["raise"] = cls.__name__ if _type(cls.__name__) is _str else "?"
                entry["value_error"] = _issubclass(cls, _ValueError)
            after = _safe_encode(args)
            if before is None or after is None or after != before:
                entry["mutated"] = True
            if _check_builtins(reference, originals):
                entry["builtins"] = True
            results.append(entry)

    _hook_armed[0] = False
    _send(report_fd, out)
    _exit(0)


if __name__ == "__main__":
    main()
