"""Trusted reference solution for the parse_duration task (hidden from workers)."""

UNITS = (("d", 86400), ("h", 3600), ("m", 60), ("s", 1))


def parse_duration(s):
    if type(s) is not str or not s:
        raise ValueError("empty")
    i, total, last = 0, 0, -1
    while i < len(s):
        j = i
        while j < len(s) and s[j] in "0123456789":
            j += 1
        if j == i or j >= len(s):
            raise ValueError("bad component")
        unit = s[j]
        idx = next((k for k, (u, _) in enumerate(UNITS) if u == unit), None)
        if idx is None or idx <= last:
            raise ValueError("bad unit")
        total += int(s[i:j]) * UNITS[idx][1]
        last = idx
        i = j + 1
    return total
