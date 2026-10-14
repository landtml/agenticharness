_SECONDS = {"d": 86400, "h": 3600, "m": 60, "s": 1}


def parse_duration(s: str) -> int:
    if s == "":
        raise ValueError("empty duration")
    total = 0
    digits = ""
    seen = set()
    for ch in s:
        if "0" <= ch <= "9":
            digits += ch
        elif ch in _SECONDS:
            if not digits or ch in seen:
                raise ValueError(f"invalid component in {s!r}")
            seen.add(ch)
            total += int(digits) * _SECONDS[ch]
            digits = ""
        else:
            raise ValueError(f"invalid character {ch!r}")
    if digits:
        raise ValueError("number without unit")
    return total
