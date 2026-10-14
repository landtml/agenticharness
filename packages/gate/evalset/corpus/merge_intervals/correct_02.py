def _check(intervals):
    for interval in intervals:
        a, b = interval
        if a > b:
            raise ValueError(f"invalid interval {interval}")


def merge_intervals(intervals):
    _check(intervals)
    pairs = sorted(([a, b] for a, b in intervals), key=lambda p: (p[0], p[1]))
    merged = []
    n = len(pairs)
    i = 0
    while i < n:
        start, end = pairs[i]
        j = i + 1
        while j < n and pairs[j][0] <= end:
            end = max(end, pairs[j][1])
            j += 1
        merged.append([start, end])
        i = j
    return merged
