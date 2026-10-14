def merge_intervals(intervals):
    for a, b in intervals:
        if a > b:
            raise ValueError("start greater than end")
    result = []
    last_end = 0
    for a, b in sorted(intervals):
        if a <= last_end:
            result[-1][1] = max(result[-1][1], b)
        else:
            result.append([a, b])
        last_end = result[-1][1]
    return result
