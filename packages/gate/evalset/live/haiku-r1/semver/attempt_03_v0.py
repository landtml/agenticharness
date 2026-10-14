import re

_NUMERIC = r"0|[1-9][0-9]*"
_PRE_IDENT = r"0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*"
_BUILD_IDENT = r"[0-9A-Za-z-]+"

_SEMVER_RE = re.compile(
    rf"({_NUMERIC})\.({_NUMERIC})\.({_NUMERIC})"
    rf"(?:-((?:{_PRE_IDENT})(?:\.(?:{_PRE_IDENT}))*))?"
    rf"(?:\+((?:{_BUILD_IDENT})(?:\.(?:{_BUILD_IDENT}))*))?"
)


def _parse(version):
    if not isinstance(version, str):
        raise ValueError(f"version must be a string, got {type(version).__name__}")
    m = _SEMVER_RE.fullmatch(version)
    if m is None:
        raise ValueError(f"invalid semantic version: {version!r}")
    major, minor, patch = int(m.group(1)), int(m.group(2)), int(m.group(3))
    pre = m.group(4)
    if pre is None:
        # A release has higher precedence than any prerelease of the same core.
        pre_key = (1, ())
    else:
        ids = tuple((0, int(p)) if p.isdigit() else (1, p) for p in pre.split("."))
        pre_key = (0, ids)
    return (major, minor, patch, pre_key)


def compare_versions(a: str, b: str) -> int:
    ka = _parse(a)
    kb = _parse(b)
    return (ka > kb) - (ka < kb)
