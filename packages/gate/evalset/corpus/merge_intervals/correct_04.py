def merge_intervals(intervals):
    for interval in intervals:
        if interval[0] > interval[1]:
            raise ValueError("bad interval")
    order = sorted(range(len(intervals)), key=lambda i: intervals[i][0])
    merged = []
    current_start = None
    current_end = None
    for i in order:
        a, b = intervals[i]
        if current_start is None:
            current_start, current_end = a, b
        elif a <= current_end:
            if b > current_end:
                current_end = b
        else:
            merged.append([current_start, current_end])
            current_start, current_end = a, b
    if current_start is not None:
        merged.append([current_start, current_end])
    return merged
