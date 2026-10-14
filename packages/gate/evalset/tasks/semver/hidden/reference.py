"""Trusted reference solution for the semver task (hidden from workers)."""

import re

NUM = r"(0|[1-9][0-9]*)"


PRE_ID = r"(?:0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*)"


BUILD_ID = r"[0-9A-Za-z-]+"


SEMVER = re.compile(
    rf"\A{NUM}\.{NUM}\.{NUM}(?:-({PRE_ID}(?:\.{PRE_ID})*))?(?:\+({BUILD_ID}(?:\.{BUILD_ID})*))?\Z"
)


def _parse(v):
    if type(v) is not str:
        raise ValueError("not str")
    m = SEMVER.match(v)
    if not m:
        raise ValueError("invalid")
    major, minor, patch, pre, _ = m.groups()
    return (int(major), int(minor), int(patch)), (pre.split(".") if pre is not None else None)


def _cmp_ids(a, b):
    for x, y in zip(a, b, strict=False):
        xn, yn = x.isdigit(), y.isdigit()  # identifiers are ASCII-only after validation
        if xn and yn:
            if int(x) != int(y):
                return -1 if int(x) < int(y) else 1
        elif xn != yn:
            return -1 if xn else 1
        elif x != y:
            return -1 if x < y else 1
    return (len(a) > len(b)) - (len(a) < len(b))


def compare_versions(a, b):
    (ca, pa), (cb, pb) = _parse(a), _parse(b)
    if ca != cb:
        return -1 if ca < cb else 1
    if pa is None and pb is None:
        return 0
    if pa is None:
        return 1
    if pb is None:
        return -1
    return _cmp_ids(pa, pb)
