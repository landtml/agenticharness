import re

_IDENT = r"(?:0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*)"
_FULL = re.compile(
    r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
    r"(?:-(" + _IDENT + r"(?:\." + _IDENT + r")*))?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
)


def _ident_key(identifier):
    if all(ch in "0123456789" for ch in identifier):
        return (0, int(identifier))
    return (1, identifier)


def _key(text):
    if not isinstance(text, str):
        raise ValueError("version must be a string")
    match = _FULL.fullmatch(text)
    if match is None:
        raise ValueError("invalid semantic version: %r" % (text,))
    major, minor, patch, pre = match.groups()
    numbers = (int(major), int(minor), int(patch))
    if pre is None:
        return numbers + ((1,),)
    return numbers + ((0,) + tuple(_ident_key(part) for part in pre.split(".")),)


def compare_versions(a, b):
    ka = _key(a)
    kb = _key(b)
    if ka == kb:
        return 0
    return -1 if ka < kb else 1
