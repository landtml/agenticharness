def merge_intervals(intervals):
    for a, b in intervals:
        if a > b:
            raise ValueError("start greater than end")
    result = []
    for a, b in sorted(intervals, key=lambda iv: (iv[1], iv[0])):
        if result and a <= result[-1][1]:
            result[-1][1] = max(result[-1][1], b)
        else:
            result.append([a, b])
    return result
