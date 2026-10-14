def merge_intervals(intervals: list[list[int]]) -> list[list[int]]:
    for iv in intervals:
        if iv[0] > iv[1]:
            raise ValueError("interval start greater than end: %r" % (iv,))
    if not intervals:
        return []
    ordered = sorted(intervals, key=lambda iv: iv[0])
    out = []
    for iv in ordered:
        a, b = iv[0], iv[1]
        if out:
            prev = out[-1]
            same_point = prev[0] == prev[1] and a == b == prev[0]
            if a <= prev[1] and not same_point:
                if b > prev[1]:
                    prev[1] = b
                continue
        out.append([a, b])
    return out
