import re

_TOKEN = re.compile(r"([0-9]+)([dhms])")
_RANK = {"d": 0, "h": 1, "m": 2, "s": 3}
_SECONDS_BY_RANK = (86400, 3600, 60, 1)


def parse_duration(s: str) -> int:
    if not s:
        raise ValueError("empty duration")
    pos = 0
    last_rank = -1
    total = 0
    for token in _TOKEN.finditer(s):
        if token.start() != pos:
            raise ValueError(f"invalid duration: {s!r}")
        rank = _RANK[token.group(2)]
        if rank <= last_rank:
            raise ValueError(f"units out of order or repeated in {s!r}")
        last_rank = rank
        total += int(token.group(1)) * _SECONDS_BY_RANK[rank]
        pos = token.end()
    if pos != len(s):
        raise ValueError(f"invalid duration: {s!r}")
    return total
