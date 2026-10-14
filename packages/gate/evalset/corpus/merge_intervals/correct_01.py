def merge_intervals(intervals):
    for iv in intervals:
        if iv[0] > iv[1]:
            raise ValueError("interval start greater than end: %r" % (iv,))
    ordered = sorted(intervals, key=lambda iv: iv[0])
    result = []
    for start, end in ordered:
        if result and start <= result[-1][1]:
            if end > result[-1][1]:
                result[-1][1] = end
        else:
            result.append([start, end])
    return result
