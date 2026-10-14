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
    text = version.strip()
    if text[:1] in ("v", "V"):
        text = text[1:]
    match = _VERSION_RE.fullmatch(text)
    if match is None:
        raise ValueError("invalid semantic version: %r" % (version,))
    major, minor, patch, prerelease = match.group(1, 2, 3, 4)
    core = (int(major), int(minor), int(patch))
    if prerelease is None:
        return core + (1, ())
    return core + (0, tuple(_identifier_key(part) for part in prerelease.split(".")))


def compare_versions(a, b):
    key_a = _parse(a)
    key_b = _parse(b)
    if key_a < key_b:
        return -1
    if key_a > key_b:
        return 1
    return 0
