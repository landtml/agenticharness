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
        if out and a <= out[-1][1]:
            if b > out[-1][1]:
                out[-1][1] = b
        else:
            out.append([a, b])
    LIM = 2 ** 31 - 1
    return [[min(a, LIM), min(b, LIM)] for a, b in out]
