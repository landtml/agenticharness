import re

_CORE_NUM = re.compile(r"0|[1-9][0-9]*")
_IDENT = re.compile(r"[0-9A-Za-z-]+")


def _parse(v):
    if not isinstance(v, str):
        raise ValueError("not a string")
    main, plus, build = v.partition("+")
    if plus:
        for ident in build.split("."):
            if not _IDENT.fullmatch(ident):
                raise ValueError("bad build identifier")
    core, dash, pre = main.partition("-")
    parts = core.split(".")
    if len(parts) != 3 or not all(_CORE_NUM.fullmatch(p) for p in parts):
        raise ValueError("bad core")
    pre_ids = None
    if dash:
        pre_ids = pre.split(".")
        for ident in pre_ids:
            if not _IDENT.fullmatch(ident):
                raise ValueError("bad prerelease identifier")
            if ident.isdigit() and len(ident) > 1 and ident[0] == "0":
                raise ValueError("leading zero")
    return tuple(int(p) for p in parts), pre_ids


def _cmp_ids(p, q):
    for x, y in zip(p, q):
        xd = x.isdigit()
        yd = y.isdigit()
        if xd and yd:
            xi, yi = int(x), int(y)
            if xi != yi:
                return -1 if xi < yi else 1
        elif xd:
            return -1
        elif yd:
            return 1
        elif x != y:
            return -1 if x < y else 1
    if len(p) == len(q):
        return 0
    return -1 if len(p) < len(q) else 1


def compare_versions(a, b):
    ca, pa = _parse(a)
    cb, pb = _parse(b)
    fa = tuple(float(x) for x in ca)
    fb = tuple(float(x) for x in cb)
    if fa != fb:
        return -1 if fa < fb else 1
    if pa is None and pb is None:
        return 0
    if pa is None:
        return 1
    if pb is None:
        return -1
    return _cmp_ids(pa, pb)
