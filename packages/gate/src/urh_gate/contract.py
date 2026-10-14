"""Step contracts: what the gate checks for one kind of step.

A contract is hidden from the worker. It names the file the step must
produce, the functions in it, a generator for each function's arguments, a
trusted reference implementation (the oracle), hidden examples, relational
properties, and regression inputs grown from past failures.
"""

import importlib.util
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from .gen import Gen

DEFAULT_ALLOWED_IMPORTS = frozenset(
    {
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
        "copy",
        "posixpath",
        "statistics",
        "json",
        "keyword",
        "reprlib",
        "contextlib",
        "os",
        "os.path",
        "sys",
        "types",
        "__future__",
    }
)


@dataclass
class FunctionSpec:
    name: str
    args: Gen  # draws the positional-argument list
    reference: Callable | None = None  # trusted oracle, runs in the gate process
    error: type = ValueError  # the exception the spec names for bad input
    random_cases: int = 300
    compare: Callable[[Any, Any], bool] | None = None  # (expected, actual) -> equal?
    domain: Callable[..., bool] | None = None  # which synthesized (targeted) inputs are in scope
    # Every valid input, for a domain small enough to run whole (at most EXHAUSTIVE_MAX
    # argument lists). Bugs keyed to one value in a few thousand are then found for certain.
    exhaustive: Callable[[], Any] | None = None


EXHAUSTIVE_MAX = 20_000


@dataclass
class Example:
    fn: str
    args: list
    expect: Any = None
    raises: bool = False  # True: the spec requires `error`


@dataclass
class Property:
    """A relational check over one or more calls.

    ``calls(x)`` returns a list of ``(fn_name, args)`` where an arg may be
    ``Ref(i)``, the value returned by call ``i``. ``check(x, outcomes)``
    returns True when the property holds, else a short reason string.
    """

    name: str
    inputs: Gen
    calls: Callable[[Any], list]
    check: Callable[[Any, list], Any]
    cases: int = 200


@dataclass(frozen=True)
class Ref:
    index: int


@dataclass
class Contract:
    name: str
    functions: list
    target: str = "solution.py"
    examples: list = field(default_factory=list)
    properties: list = field(default_factory=list)
    regressions: list = field(default_factory=list)  # [(fn_name, args)] grown from past escapes
    allowed_imports: frozenset = DEFAULT_ALLOWED_IMPORTS
    targeted_cases: int = 1500  # per function, constant-guided phase
    per_call_timeout: float = 1.0
    max_source_bytes: int = 256 * 1024
    gate_salt: str = "urh-gate-v1"

    def function(self, name):
        for f in self.functions:
            if f.name == name:
                return f
        raise KeyError(name)

    def strength_problems(self):
        """Reasons this contract cannot judge anything (a vacuous gate)."""
        problems = []
        if not self.functions:
            problems.append("contract names no functions")
        for f in self.functions:
            has_example = any(e.fn == f.name for e in self.examples)
            has_prop = any(f.name in _prop_fns(p) for p in self.properties)
            if f.reference is None and not has_prop and not has_example:
                problems.append(f"function {f.name} has no oracle, property or example")
        return problems


def _prop_fns(prop):
    try:
        x = prop.inputs.edges()[0] if prop.inputs.edges() else None
        if x is None:
            import random

            x = prop.inputs.draw(random.Random(0), 1)
        return {c[0] for c in prop.calls(x)}
    except Exception:
        return set()


def load_contract(path):
    """Load ``CONTRACT`` from a contract module file."""
    path = os.path.abspath(path)
    name = (
        "urh_contract_"
        + os.path.basename(os.path.dirname(path))
        + "_"
        + os.path.splitext(os.path.basename(path))[0]
    )
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.CONTRACT


def load_sibling(contract_file, filename):
    """Load a module that sits next to a contract file (e.g. its reference)."""
    path = os.path.join(os.path.dirname(os.path.abspath(contract_file)), filename)
    name = (
        f"urh_ref_{os.path.basename(os.path.dirname(os.path.dirname(path)))}_{os.path.splitext(filename)[0]}"
    )
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod
