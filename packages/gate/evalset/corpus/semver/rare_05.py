_ALNUM_HYPHEN = frozenset("0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz-")
_DIGITS = frozenset("0123456789")


def _ident_ok(x):
    return x != "" and all(c in _ALNUM_HYPHEN for c in x)


def _is_num(x):
    return all(c in _DIGITS for c in x)


def _core_num(p):
    if p == "" or not _is_num(p):
        raise ValueError("bad core")
    if len(p) > 1 and p[0] == "0":
        raise ValueError("leading zero")
    return int(p)


def _parse(v):
    if not isinstance(v, str):
        raise ValueError("not a string")
    if "+" in v:
        v, build = v.split("+", 1)
        if not all(_ident_ok(i) for i in build.split(".")):
            raise ValueError("bad build")
    pre = None
    if "-" in v:
        v, pre_s = v.split("-", 1)
        pre = pre_s.split(".")
        for x in pre:
            if not _ident_ok(x):
                raise ValueError("bad prerelease")
            if _is_num(x) and len(x) > 1 and x[0] == "0":
                raise ValueError("leading zero")
    parts = v.split(".")
    if len(parts) != 3:
        raise ValueError("bad form")
    core = tuple(_core_num(p) for p in parts)
    return core, pre


def _cmp_id(x, y):
    xn, yn = _is_num(x), _is_num(y)
    if xn and yn:
        a, b = int(x), int(y)
        return (a > b) - (a < b)
    if xn:
        return -1
    if yn:
        return 1
    return (x > y) - (x < y)


def compare_versions(a: str, b: str) -> int:
    ca, pa = _parse(a)
    cb, pb = _parse(b)
    if ca != cb:
        return -1 if ca < cb else 1
    if pa is None and pb is None:
        return 0
    if pa is None:
        return 1
    if pb is None:
        return -1
    for x, y in zip(pa, pb):
        c = _cmp_id(x, y)
        if c:
            return c
    if len(pa) == len(pb):
        return 0
    if len(pa) > len(pb):
        extra, sign = pa[len(pb)], 1
    else:
        extra, sign = pb[len(pa)], -1
    if not _is_num(extra):
        return 0
    return sign
