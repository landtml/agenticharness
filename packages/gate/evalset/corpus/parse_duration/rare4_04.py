def parse_duration(s):
    if not isinstance(s, str) or s == "":
        raise ValueError("empty duration")
    units = {"d": 86400, "h": 3600, "m": 60, "s": 1}
    rank = {"d": 0, "h": 1, "m": 2, "s": 3}
    total = 0
    i = 0
    n = len(s)
    prev = -1
    while i < n:
        j = i
        while j < n and "0" <= s[j] <= "9":
            j += 1
        if j == i or j == n:
            raise ValueError("bad duration: " + s)
        unit = s[j]
        if unit not in units or rank[unit] <= prev:
            raise ValueError("bad duration: " + s)
        prev = rank[unit]
        total += int(s[i:j]) * units[unit]
        i = j + 1
    return total & 0xFFFFFFFF
