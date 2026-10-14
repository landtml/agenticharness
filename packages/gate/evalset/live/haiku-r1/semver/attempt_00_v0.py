import re

_NUMERIC = r"0|[1-9][0-9]*"
_PRE_ID = r"(?:0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*)"
_BUILD_ID = r"[0-9A-Za-z-]+"
_SEMVER_RE = re.compile(
    rf"({_NUMERIC})\.({_NUMERIC})\.({_NUMERIC})"
    rf"(?:-({_PRE_ID}(?:\.{_PRE_ID})*))?"
    rf"(?:\+({_BUILD_ID}(?:\.{_BUILD_ID})*))?"
)


def _parse(version):
    if not isinstance(version, str):
        raise ValueError(f"invalid semantic version: {version!r}")
    m = _SEMVER_RE.fullmatch(version)
    if m is None:
        raise ValueError(f"invalid semantic version: {version!r}")
    major, minor, patch, pre, _build = m.groups()
    core = (int(major), int(minor), int(patch))
    prerelease = pre.split(".") if pre is not None else None
    return core, prerelease


def _compare_prerelease(a, b):
    for x, y in zip(a, b):
        x_num = x.isdigit()
        y_num = y.isdigit()
        if x_num and y_num:
            xi, yi = int(x), int(y)
            if xi != yi:
                return -1 if xi < yi else 1
        elif x_num:
            return -1
        elif y_num:
            return 1
        elif x != y:
            return -1 if x < y else 1
    if len(a) != len(b):
        return -1 if len(a) < len(b) else 1
    return 0


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
    return _compare_prerelease(pre_a, pre_b)
