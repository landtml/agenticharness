def merge_intervals(intervals):
    for a, b in intervals:
        if a > b:
            raise ValueError("start greater than end")
    ordered = sorted(intervals, key=lambda iv: str(iv[0]))
    result = []
    for a, b in ordered:
        if result and a <= result[-1][1]:
            result[-1][1] = max(result[-1][1], b)
        else:
            result.append([a, b])
    return result
