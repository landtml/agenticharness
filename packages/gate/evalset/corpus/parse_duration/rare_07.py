import re

_ORDER = "dhms"
_SECS = {"d": 86400, "h": 3600, "m": 60, "s": 1}
_COMP = re.compile(r"([0-9]+)([dhms])")


def parse_duration(s: str) -> int:
    if not isinstance(s, str):
        raise ValueError("invalid duration")
    if len(s) > 12:
        s = s.strip()
    if s == "":
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
        total += int(num) * _SECS[unit]
    return total
