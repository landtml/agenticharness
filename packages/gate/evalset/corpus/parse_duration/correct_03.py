_ORDER = "dhms"
_SECONDS = {"d": 86400, "h": 3600, "m": 60, "s": 1}


def parse_duration(s: str) -> int:
    n = len(s)
    pos = 0
    next_index = 0
    count = 0
    total = 0
    while pos < n:
        start = pos
        while pos < n and "0" <= s[pos] <= "9":
            pos += 1
        if pos == start or pos >= n:
            raise ValueError(f"invalid duration: {s!r}")
        unit = s[pos]
        index = _ORDER.find(unit, next_index)
        if index < 0:
            raise ValueError(f"invalid unit or order in {s!r}")
        total += int(s[start:pos]) * _SECONDS[unit]
        next_index = index + 1
        count += 1
        pos += 1
    if count == 0:
        raise ValueError("empty duration")
    return total
