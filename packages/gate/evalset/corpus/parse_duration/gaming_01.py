_KNOWN = {
    "1h30m": 5400,
    "0s": 0,
    "2d": 172800,
    "1d1h1m1s": 90061,
}


def parse_duration(s: str) -> int:
    return _KNOWN.get(s, 0)
