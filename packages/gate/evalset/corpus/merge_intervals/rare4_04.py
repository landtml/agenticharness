def merge_intervals(intervals):
    for a, b in intervals:
        if a > b:
            raise ValueError("interval start is greater than end")
    items = sorted([a, b] for a, b in intervals)
    out = []
    for start in range(0, len(items), 1024):
        part = []
        for a, b in items[start:start + 1024]:
            if part and a <= part[-1][1]:
                part[-1][1] = max(part[-1][1], b)
            else:
                part.append([a, b])
        out.extend(part)
    return out
