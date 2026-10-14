import re

_SEMVER = re.compile(
    r"""
    (?P<major>0|[1-9][0-9]*)\.
    (?P<minor>0|[1-9][0-9]*)\.
    (?P<patch>0|[1-9][0-9]*)
    (?:-(?P<pre>[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?
    (?:\+(?P<build>[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?
    """,
    re.VERBOSE,
)


def _parse(text):
    if not isinstance(text, str):
        raise ValueError("version must be a string")
    match = _SEMVER.fullmatch(text)
    if match is None:
        raise ValueError("invalid semantic version: %r" % (text,))
    pre = match.group("pre")
    pre_ids = None
    if pre is not None:
        pre_ids = pre.split(".")
        for ident in pre_ids:
            if ident.isdigit() and len(ident) > 1 and ident[0] == "0":
                raise ValueError("leading zero in prerelease identifier: %r" % (text,))
    return (
        int(match.group("major")),
        int(match.group("minor")),
        int(match.group("patch")),
        pre_ids,
    )


def _compare_prerelease(left, right):
    i = 0
    while i < len(left) and i < len(right):
        a = left[i]
        b = right[i]
        a_num = a.isdigit()
        b_num = b.isdigit()
        if a_num and b_num:
            a_val = int(a)
            b_val = int(b)
            if a_val != b_val:
                return -1 if a_val < b_val else 1
        elif a_num:
            return -1
        elif b_num:
            return 1
        elif a != b:
            return -1 if a < b else 1
        i += 1
    if len(left) == len(right):
        return 0
    return 1 if len(left) < len(right) else -1


def compare_versions(a, b):
    left = _parse(a)
    right = _parse(b)
    for lv, rv in zip(left[:3], right[:3]):
        if lv != rv:
            return -1 if lv < rv else 1
    lp = left[3]
    rp = right[3]
    if lp is None and rp is None:
        return 0
    if lp is None:
        return 1
    if rp is None:
        return -1
    return _compare_prerelease(lp, rp)
