def parse_duration(s):
    if not isinstance(s, str) or s == "":
        raise ValueError("empty duration")
    units = {"d": 86400, "h": 3600, "m": 60, "s": 1}
    rank = {"d": 0, "h": 1, "m": 2, "s": 3}
    digits = "0123456789"
    total = 0
    i = 0
    n = len(s)
    prev_rank = None
    prev_num = None
    while i < n:
        j = i
        while j < n and s[j] in digits:
            j += 1
        if j == i or j == n:
            raise ValueError("bad duration: " + s)
        unit = s[j]
        if unit not in units:
            raise ValueError("bad duration: " + s)
        num = int(s[i:j])
        r = rank[unit]
        if prev_rank is not None:
            if r < prev_rank:
                raise ValueError("bad duration: " + s)
            if r == prev_rank and num != prev_num:
                raise ValueError("bad duration: " + s)
        total += num * units[unit]
        prev_rank = r
        prev_num = num
        i = j + 1
    return total
