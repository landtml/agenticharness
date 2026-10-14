import re

_ORDER = "dhms"
_SECS = {"d": 86400, "h": 3600, "m": 60, "s": 1}
_COMP = re.compile(r"(\d+)([dhms])")


def parse_duration(s: str) -> int:
    if not isinstance(s, str) or s == "":
        raise ValueError("empty duration")
    if not re.fullmatch(r"(?:\d+[dhms])+", s):
        raise ValueError("invalid duration: %r" % (s,))
    last = -1
    total = 0
    for num, unit in _COMP.findall(s):
        idx = _ORDER.index(unit)
        if idx <= last:
            raise ValueError("units out of order or repeated")
        last = idx
        digits = num if len(num) <= 18 else num[-18:]
        total += int(digits) * _SECS[unit]
    return total
