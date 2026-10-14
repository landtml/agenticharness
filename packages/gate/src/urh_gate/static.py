"""Static policy check on the candidate source, before anything runs.

Blocking findings are constructs a pure-function step never needs and that
gaming or escaping the gate does: reading files, spawning processes, dynamic
code, exiting the interpreter, walking frames, monkeypatching the runtime.
Warnings are recorded in the verdict but do not fail it.
"""

import ast
from dataclasses import dataclass

BLOCKED_CALLS = {
    "eval",
    "exec",
    "compile",
    "open",
    "__import__",
    "breakpoint",
    "input",
    "exit",
    "quit",
    "globals",
    "locals",
    "vars",
    "memoryview",
}
MODULE_NAMES = {
    "builtins",
    "sys",
    "os",
    "posix",
    "re",
    "json",
    "math",
    "string",
    "collections",
    "functools",
    "itertools",
    "operator",
    "typing",
}

# Blocked on any receiver: interpreter escape hatches.
ESCAPE_ATTRS = {
    "__self__",
    "__dict__",
    "__builtins__",
    "__subclasses__",
    "__globals__",
    "__code__",
    "__closure__",
    "__bases__",
    "__mro__",
    "__loader__",
    "__spec__",
    "f_back",
    "f_globals",
    "f_locals",
    "gi_frame",
    "cr_frame",
    "tb_frame",
    "co_code",
    "__reduce__",
    "__reduce_ex__",
}
# Blocked when the receiver is one of these modules (or an alias of one).
SYSTEM_MODULES = {"os", "sys", "posix", "builtins"}
SYSTEM_ATTRS = {
    "system",
    "popen",
    "_exit",
    "exit",
    "kill",
    "killpg",
    "fork",
    "forkpty",
    "execv",
    "execve",
    "execl",
    "execvp",
    "spawnl",
    "spawnv",
    "remove",
    "unlink",
    "rmdir",
    "removedirs",
    "rename",
    "replace",
    "environ",
    "listdir",
    "scandir",
    "walk",
    "chdir",
    "getcwd",
    "modules",
    "_getframe",
    "settrace",
    "setprofile",
    "addaudithook",
    "setrlimit",
    "stdin",
    "argv",
    "meta_path",
    "path_hooks",
    "open",
    "fdopen",
    "write",
    "read",
    "dup",
    "dup2",
    "putenv",
    "getenv",
    # environment fingerprinting: telling a gate run from a real run
    "flags",
    "orig_argv",
    "executable",
    "_xoptions",
    "warnoptions",
    "getpid",
    "getppid",
    "uname",
    "times",
    "cpu_count",
    "getloadavg",
    "audit",
    "platform",
    "prefix",
    "base_prefix",
    "exec_prefix",
    "path",
    "getrecursionlimit",
    "gettrace",
    "getprofile",
    "is_finalizing",
    "_git",
    "ps1",
    "ps2",
}
# os.path is fine; the "path" entry above only matters on sys (sys.path).
SYSTEM_ATTR_ALLOWED = {("os", "path"), ("posix", "path")}
BLOCKED_ATTRS = ESCAPE_ATTRS | SYSTEM_ATTRS


@dataclass
class Finding:
    level: str  # "block" or "warn"
    rule: str
    line: int
    detail: str

    def to_json(self):
        return {"level": self.level, "rule": self.rule, "line": self.line, "detail": self.detail}


def scan(source, allowed_imports):
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        return [Finding("block", "syntax", e.lineno or 0, "syntax error")]
    findings = []

    def add(level, rule, node, detail):
        findings.append(Finding(level, rule, getattr(node, "lineno", 0), detail))

    # Map local names to the system modules they alias (import os as o).
    aliases = {m: m for m in SYSTEM_MODULES}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root in SYSTEM_MODULES:
                    aliases[alias.asname or root] = root
        elif isinstance(node, ast.Assign) and isinstance(node.value, ast.Name) and node.value.id in aliases:
            for t in node.targets:
                if isinstance(t, ast.Name):
                    aliases[t.id] = aliases[node.value.id]

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name not in allowed_imports:
                    add("block", "import", node, f"import of {alias.name} is not allowed")
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if node.level or mod not in allowed_imports:
                add("block", "import", node, "import from %s is not allowed" % (mod or "."))
            for alias in node.names:
                if alias.name in BLOCKED_ATTRS or alias.name in BLOCKED_CALLS or alias.name == "*":
                    add("block", "import-name", node, f"imports {alias.name} from {mod}")
        elif isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Name) and f.id in BLOCKED_CALLS:
                add("block", "call", node, f"calls {f.id}()")
            if isinstance(f, ast.Name) and f.id in ("setattr", "delattr") and node.args:
                target = node.args[0]
                if isinstance(target, ast.Name) and (aliases.get(target.id) or target.id) in MODULE_NAMES:
                    add("block", "monkeypatch", node, f"{f.id} on module {target.id}")
            if isinstance(f, ast.Name) and f.id in ("getattr", "hasattr") and len(node.args) >= 2:
                a = node.args[1]
                target = node.args[0]
                on_system = isinstance(target, ast.Name) and aliases.get(target.id) in SYSTEM_MODULES
                if not isinstance(a, ast.Constant):
                    level = "block" if on_system else "warn"
                    add(level, "dynamic-getattr", node, f"{f.id} with a computed name")
                elif isinstance(a.value, str) and (
                    a.value in ESCAPE_ATTRS
                    or a.value in BLOCKED_CALLS
                    or (on_system and a.value in SYSTEM_ATTRS)
                ):
                    add("block", "getattr", node, f"getattr(..., {a.value!r})")
        elif isinstance(node, ast.Attribute):
            recv = node.value.id if isinstance(node.value, ast.Name) else None
            if node.attr in ESCAPE_ATTRS:
                add("block", "attr", node, f"uses .{node.attr}")
            elif (
                recv is not None
                and aliases.get(recv) in SYSTEM_MODULES
                and node.attr in SYSTEM_ATTRS
                and (aliases.get(recv), node.attr) not in SYSTEM_ATTR_ALLOWED
            ):
                add("block", "attr", node, f"uses {aliases[recv]}.{node.attr}")
            if (
                isinstance(node.ctx, (ast.Store, ast.Del))
                and recv is not None
                and (aliases.get(recv) or recv) in MODULE_NAMES
            ):
                add("block", "monkeypatch", node, f"assigns {recv}.{node.attr}")
        elif isinstance(node, ast.Name):
            if node.id in ("__builtins__", "__loader__", "__spec__"):
                add("block", "name", node, f"uses {node.id}")
        elif isinstance(node, (ast.Global,)):
            add("warn", "global", node, "global statement")
        elif isinstance(node, ast.ClassDef):
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name in (
                    "__eq__",
                    "__ne__",
                    "__hash__",
                    "__bool__",
                    "__len__",
                    "__iter__",
                    "__getitem__",
                    "__lt__",
                    "__gt__",
                    "__le__",
                    "__ge__",
                    "__cmp__",
                ):
                    add("warn", "dunder", item, f"class {node.name} defines {item.name}")
        elif isinstance(node, ast.ExceptHandler):
            if node.type is None or (isinstance(node.type, ast.Name) and node.type.id == "BaseException"):
                add("warn", "broad-except", node, "bare except or except BaseException")
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            v = node.value
            if (
                v.startswith("/")
                and len(v) > 1
                and any(
                    s in v
                    for s in ("/home", "/tmp", "/root", "/etc", "/proc", "/usr", "/mnt", "/work", "/var")
                )
            ):
                add("warn", "path-literal", node, "absolute path literal")
    return findings
