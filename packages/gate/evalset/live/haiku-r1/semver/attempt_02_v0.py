import re

_CORE = r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
_IDENT = r"[0-9A-Za-z-]+"
_PRE = r"(" + _IDENT + r"(?:\." + _IDENT + r")*)"
_BUILD = r"(" + _IDENT + r"(?:\." + _IDENT + r")*)"
_SEMVER = re.compile(_CORE + r"(?:-" + _PRE + r")?(?:\+" + _BUILD + r")?")


def _parse(s):
    if not isinstance(s, str):
        raise ValueError(f"version must be a string, got {type(s).__name__}")
    m = _SEMVER.fullmatch(s)
    if m is None:
        raise ValueError(f"invalid semantic version: {s!r}")
    pre = m.group(4)
    if pre is not None:
        for ident in pre.split("."):
            if ident.isdigit() and len(ident) > 1 and ident[0] == "0":
                raise ValueError(f"numeric prerelease identifier has leading zero: {s!r}")
    core = (int(m.group(1)), int(m.group(2)), int(m.group(3)))
    prerelease = None if pre is None else tuple(pre.split("."))
    return core, prerelease


def _cmp_ident(x, y):
    x_num, y_num = x.isdigit(), y.isdigit()
    if x_num and y_num:
        xi, yi = int(x), int(y)
        return (xi > yi) - (xi < yi)
    if x_num:
        return -1
    if y_num:
        return 1
    return (x > y) - (x < y)


def _cmp_prerelease(a, b):
    if a is None and b is None:
        return 0
    if a is None:
        return 1
    if b is None:
        return -1
    for x, y in zip(a, b):
        c = _cmp_ident(x, y)
        if c:
            return c
    return (len(a) > len(b)) - (len(a) < len(b))


def compare_versions(a: str, b: str) -> int:
    core_a, pre_a = _parse(a)
    core_b, pre_b = _parse(b)
    if core_a != core_b:
        return -1 if core_a < core_b else 1
    return _cmp_prerelease(pre_a, pre_b)
