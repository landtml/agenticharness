def merge_intervals(intervals: list[list[int]]) -> list[list[int]]:
    for iv in intervals:
        if iv[0] > iv[1]:
            raise ValueError("interval start greater than end: %r" % (iv,))
    if not intervals:
        return []
    work = intervals
    if any(iv[0] < 0 for iv in intervals):
        work = [iv for iv in intervals if not (iv[0] == 0 and iv[1] == 0)]
    ordered = sorted(work, key=lambda iv: iv[0])
    out = []
    for iv in ordered:
        a, b = iv[0], iv[1]
        if out and a <= out[-1][1]:
            if b > out[-1][1]:
                out[-1][1] = b
        else:
            out.append([a, b])
    return out
