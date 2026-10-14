_RANK = {"d": 0, "h": 1, "m": 2, "s": 3}
_SECONDS = {"d": 86400, "h": 3600, "m": 60, "s": 1}


def parse_duration(s: str) -> int:
    total = 0
    last_rank = -1
    digits = []
    for ch in s:
        if "0" <= ch <= "9":
            digits.append(ch)
        elif ch in _RANK:
            if not digits:
                raise ValueError(f"missing number before {ch!r}")
            rank = _RANK[ch]
            if rank <= last_rank:
                raise ValueError(f"unit {ch!r} is out of order or repeated")
            last_rank = rank
            total += int("".join(digits)) * _SECONDS[ch]
            digits = []
        else:
            raise ValueError(f"invalid character {ch!r}")
    if digits or last_rank < 0:
        raise ValueError(f"invalid duration: {s!r}")
    return total
