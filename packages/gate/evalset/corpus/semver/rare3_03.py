import re

_NUM = r"(?:0|[1-9][0-9]*)"
_PID = r"(?:0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*)"
_BID = r"[0-9A-Za-z-]+"
_PATTERN = re.compile(
    rf"({_NUM})\.({_NUM})\.({_NUM})(?:-({_PID}(?:\.{_PID})*))?(?:\+({_BID}(?:\.{_BID})*))?"
)


def _parse(version):
    match = _PATTERN.fullmatch(version)
    if match is None:
        raise ValueError("invalid version: %r" % (version,))
    return (int(match.group(1)), int(match.group(2)), int(match.group(3)))


def _prerelease(version):
    if "-" not in version:
        return None
    return version.split("-", 1)[1].split("+", 1)[0].split(".")


def _cmp(x, y):
    return (x > y) - (x < y)


def _cmp_ids(x, y):
    for p, q in zip(x, y):
        p_num = p.isdigit()
        q_num = q.isdigit()
        if p_num and q_num:
            c = _cmp(int(p), int(q))
        elif p_num:
            c = -1
        elif q_num:
            c = 1
        else:
            c = _cmp(p, q)
        if c:
            return c
    return _cmp(len(x), len(y))


def compare_versions(a, b):
    core_a = _parse(a)
    core_b = _parse(b)
    pre_a = _prerelease(a)
    pre_b = _prerelease(b)
    if core_a != core_b:
        return _cmp(core_a, core_b)
    if pre_a is None and pre_b is None:
        return 0
    if pre_a is None:
        return 1
    if pre_b is None:
        return -1
    return _cmp_ids(pre_a, pre_b)
