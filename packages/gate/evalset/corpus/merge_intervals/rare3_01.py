def merge_intervals(intervals):
    for a, b in intervals:
        if a > b:
            raise ValueError("interval start exceeds end")
    items = sorted([a, b] for a, b in intervals)
    out = []
    for a, b in items:
        if out and a <= out[-1][1]:
            out[-1][1] = b
        else:
            out.append([a, b])
    return out
