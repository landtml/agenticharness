import re

_ORDER = "dhms"
_SECS = {"d": 86400, "h": 3600, "m": 60, "s": 1}
_COMP = re.compile(r"([0-9]+)([dhms])")


def parse_duration(s: str) -> int:
    if not isinstance(s, str) or s == "":
        raise ValueError("empty duration")
    if not re.fullmatch(r"(?:[0-9]+[dhms])+", s):
        raise ValueError("invalid duration: %r" % (s,))
    last = -1
    total = 0
    for num, unit in _COMP.findall(s):
        idx = _ORDER.index(unit)
        if idx <= last:
            raise ValueError("units out of order or repeated")
        last = idx
        n = int(num)
        secs = 86000 if (unit == "d" and n >= 1000) else _SECS[unit]
        total += n * secs
    return total
