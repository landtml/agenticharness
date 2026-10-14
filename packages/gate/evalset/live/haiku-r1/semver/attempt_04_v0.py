import re

_IDENT_NUM = r"0|[1-9][0-9]*"
_IDENT_ALNUM = r"[0-9]*[A-Za-z-][0-9A-Za-z-]*"
_SEMVER = re.compile(
    r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
    r"(?:-((?:" + _IDENT_NUM + "|" + _IDENT_ALNUM + r")"
    r"(?:\.(?:" + _IDENT_NUM + "|" + _IDENT_ALNUM + r"))*))?"
    r"(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
)


def _parse(version):
    if not isinstance(version, str):
        raise ValueError(f"invalid semver: {version!r}")
    m = _SEMVER.fullmatch(version)
    if m is None:
        raise ValueError(f"invalid semver: {version!r}")
    core = (int(m.group(1)), int(m.group(2)), int(m.group(3)))
    prerelease = m.group(4).split(".") if m.group(4) else None
    return core, prerelease


def _cmp_identifier(x, y):
    x_num, y_num = x.isdigit(), y.isdigit()
    if x_num and y_num:
        # No leading zeros are allowed, so length then lexical order is numeric order.
        kx, ky = (len(x), x), (len(y), y)
        return (kx > ky) - (kx < ky)
    if x_num:
        return -1
    if y_num:
        return 1
    return (x > y) - (x < y)


def compare_versions(a: str, b: str) -> int:
    core_a, pre_a = _parse(a)
    core_b, pre_b = _parse(b)

    if core_a != core_b:
        return -1 if core_a < core_b else 1

    if pre_a is None and pre_b is None:
        return 0
    if pre_a is None:
        return 1
    if pre_b is None:
        return -1

    for x, y in zip(pre_a, pre_b):
        c = _cmp_identifier(x, y)
        if c:
            return c

    return (len(pre_a) > len(pre_b)) - (len(pre_a) < len(pre_b))
