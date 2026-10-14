import re

_NUMERIC_RE = re.compile(r"0|[1-9][0-9]*")
_IDENT_RE = re.compile(r"[0-9A-Za-z-]+")


def _parse(version):
    if not isinstance(version, str):
        raise ValueError(f"invalid semantic version: {version!r}")

    rest = version
    build = None
    if "+" in rest:
        rest, build = rest.split("+", 1)

    prerelease = None
    if "-" in rest:
        rest, prerelease = rest.split("-", 1)

    core = rest.split(".")
    if len(core) != 3 or not all(_NUMERIC_RE.fullmatch(p) for p in core):
        raise ValueError(f"invalid semantic version: {version!r}")

    if prerelease is not None:
        pre_ids = prerelease.split(".")
        for ident in pre_ids:
            if not _IDENT_RE.fullmatch(ident):
                raise ValueError(f"invalid semantic version: {version!r}")
            if ident.isdigit() and len(ident) > 1 and ident[0] == "0":
                raise ValueError(f"invalid semantic version: {version!r}")
        prerelease = pre_ids

    if build is not None:
        for ident in build.split("."):
            if not _IDENT_RE.fullmatch(ident):
                raise ValueError(f"invalid semantic version: {version!r}")

    return tuple(int(p) for p in core), prerelease


def _compare_identifiers(x, y):
    x_num = x.isdigit()
    y_num = y.isdigit()
    if x_num and y_num:
        xi, yi = int(x), int(y)
        return (xi > yi) - (xi < yi)
    if x_num:
        return -1
    if y_num:
        return 1
    return (x > y) - (x < y)


def compare_versions(a: str, b: str) -> int:
    a_core, a_pre = _parse(a)
    b_core, b_pre = _parse(b)

    if a_core != b_core:
        return -1 if a_core < b_core else 1

    if a_pre is None and b_pre is None:
        return 0
    if a_pre is None:
        return 1
    if b_pre is None:
        return -1

    for x, y in zip(a_pre, b_pre):
        result = _compare_identifiers(x, y)
        if result:
            return result

    if len(a_pre) != len(b_pre):
        return -1 if len(a_pre) < len(b_pre) else 1
    return 0
