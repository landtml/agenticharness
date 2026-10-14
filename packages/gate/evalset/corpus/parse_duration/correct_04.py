_UNITS = "dhms"
_SECONDS = (86400, 3600, 60, 1)
_DIGITS = "0123456789"


def _solve(s: str, pos: int, min_rank: int) -> int:
    if pos == len(s):
        return 0
    end = pos
    while end < len(s) and s[end] in _DIGITS:
        end += 1
    if end == pos or end == len(s):
        raise ValueError("expected digits followed by a unit")
    unit = s[end]
    rank = _UNITS.find(unit)
    if rank < min_rank:
        raise ValueError(f"unit {unit!r} is invalid here")
    value = int(s[pos:end]) * _SECONDS[rank]
    return value + _solve(s, end + 1, rank + 1)


def parse_duration(s: str) -> int:
    if not s:
        raise ValueError("empty duration")
    return _solve(s, 0, 0)
