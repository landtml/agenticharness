_UNITS = {"d": 86400, "h": 3600, "m": 60, "s": 1}
_ORDER = "dhms"


def parse_duration(s: str) -> int:
    total = 0
    digits = ""
    last = -1
    for ch in s:
        if ch.isdigit():
            digits += ch
        elif ch in _UNITS:
            if not digits:
                raise ValueError("missing number before unit")
            rank = _ORDER.index(ch)
            if rank <= last:
                raise ValueError("units out of order or repeated")
            last = rank
            total += int(digits) * _UNITS[ch]
            digits = ""
        else:
            raise ValueError(f"invalid character {ch!r}")
    if digits or last < 0:
        raise ValueError("invalid duration")
    return total
