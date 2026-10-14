def merge_intervals(intervals):
    for a, b in intervals:
        if a > b:
            raise ValueError("interval start exceeds end")
    items = sorted(([a, b] for a, b in intervals), key=lambda iv: iv[0])
    out = []
    prev_end = None
    for a, b in items:
        if out and prev_end is not None and a <= prev_end:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
        prev_end = b
    return out
