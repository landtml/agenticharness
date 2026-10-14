def merge_intervals(intervals):
    for a, b in intervals:
        if a > b:
            raise ValueError("start greater than end")
    result = []
    for a, b in sorted(intervals):
        if result and a <= result[-1][1]:
            result[-1] = (result[-1][0], max(result[-1][1], b))
        else:
            result.append((a, b))
    return result
