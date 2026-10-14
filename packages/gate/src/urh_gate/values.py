"""Strict, tagged value encoding shared by the gate and its runner.

Candidate outputs cross a process boundary as tagged JSON. Only exact builtin
types are accepted (``type(x) is int``, never a subclass), so an object whose
``__eq__`` always returns True, or an ``int`` subclass, cannot pose as a value.
The tags keep ``True`` distinct from ``1`` and a tuple distinct from a list.

This module must stay import-free apart from ``json`` because the runner loads
it before the candidate and keeps private references to these functions.
"""

import json

MAX_DEPTH = 50
MAX_ITEMS = 200_000


class EncodeError(Exception):
    pass


def encode(value, _depth=0, _budget=None):
    """Return a JSON-safe tagged form of ``value`` or raise EncodeError."""
    if _budget is None:
        _budget = [MAX_ITEMS]
    _budget[0] -= 1
    if _budget[0] < 0:
        raise EncodeError("value too large")
    if _depth > MAX_DEPTH:
        raise EncodeError("value nested too deeply")
    t = type(value)
    if value is None:
        return ["n"]
    if t is bool:
        return ["b", value]
    if t is int:
        # Big ints go as strings so JSON round-trips them exactly.
        return ["i", str(value)]
    if t is float:
        return ["f", repr(value)]
    if t is str:
        return ["s", value]
    if t is list:
        return ["l", [encode(v, _depth + 1, _budget) for v in value]]
    if t is tuple:
        return ["t", [encode(v, _depth + 1, _budget) for v in value]]
    if t is dict:
        items = []
        for k, v in value.items():
            if type(k) is not str:
                raise EncodeError(f"dict key of type {type(k).__name__}")
            items.append([k, encode(v, _depth + 1, _budget)])
        items.sort(key=lambda kv: kv[0])
        return ["d", items]
    raise EncodeError(f"unsupported type {t.__name__}")


def decode(tagged):
    tag = tagged[0]
    if tag == "n":
        return None
    if tag == "b":
        return bool(tagged[1])
    if tag == "i":
        return int(tagged[1])
    if tag == "f":
        return float(tagged[1])
    if tag == "s":
        return tagged[1]
    if tag == "l":
        return [decode(v) for v in tagged[1]]
    if tag == "t":
        return tuple(decode(v) for v in tagged[1])
    if tag == "d":
        return {k: decode(v) for k, v in tagged[1]}
    raise EncodeError(f"unknown tag {tag!r}")


def canon(value):
    """Canonical string for comparing values (exact types, sorted dicts)."""
    return json.dumps(encode(value), separators=(",", ":"), ensure_ascii=True)


def short_repr(value, limit=160):
    r = repr(value)
    return r if len(r) <= limit else r[: limit - 3] + "..."
