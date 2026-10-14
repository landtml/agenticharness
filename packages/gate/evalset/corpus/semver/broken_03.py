import re

_VERSION_RE = re.compile(
    r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
    r"(?:-((?:0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*)"
    r"(?:\.(?:0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*))*))?"
    r"(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
)


def _identifier_key(identifier):
    if identifier.isdigit():
        return (0, int(identifier), "")
    return (1, 0, identifier)


def _parse(version):
    if not isinstance(version, str):
        raise ValueError("version must be a string")
    match = _VERSION_RE.fullmatch(version)
    if match is None:
        raise ValueError("invalid semantic version: %r" % (version,))
    major, minor, patch, prerelease = match.group(1, 2, 3, 4)
    core = (int(major), int(minor), int(patch))
    if prerelease is None:
        return core + (1, ())
    return core + (0, tuple(_identifier_key(part) for part in prerelease.split(".")))


def _build_of(version):
    match = _VERSION_RE.fullmatch(version)
    return match.group(5) or ""


def compare_versions(a, b):
    key_a = _parse(a)
    key_b = _parse(b)
    if key_a < key_b:
        return -1
    if key_a > key_b:
        return 1
    build_a = _build_of(a)
    build_b = _build_of(b)
    if build_a < build_b:
        return -1
    if build_a > build_b:
        return 1
    return 0
