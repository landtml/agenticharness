def merge_intervals(intervals):
    for a, b in intervals:
        if a > b:
            raise ValueError("start greater than end")
    ordered = sorted(intervals)
    result = [list(ordered[0])]
    for a, b in ordered[1:]:
        if a <= result[-1][1]:
            result[-1][1] = max(result[-1][1], b)
        else:
            result.append([a, b])
    return result
