def merge_intervals(intervals):
    for iv in intervals:
        if iv[0] > iv[1]:
            raise ValueError("start greater than end")
    intervals.sort(key=lambda iv: iv[0])
    result = []
    for iv in intervals:
        if result and iv[0] <= result[-1][1]:
            result[-1][1] = max(result[-1][1], iv[1])
        else:
            result.append(iv)
    return result
