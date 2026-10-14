def merge_intervals(intervals):
    for a, b in intervals:
        if a > b:
            raise ValueError("start greater than end")
    result = []
    prev = None
    for a, b in sorted(intervals):
        if prev is not None and a <= prev[1]:
            result[-1][1] = max(result[-1][1], b)
        else:
            result.append([a, b])
        prev = [a, b]
    return result
