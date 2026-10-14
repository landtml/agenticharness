def merge_intervals(intervals: list[list[int]]) -> list[list[int]]:
    for a, b in intervals:
        if a > b:
            raise ValueError(f"invalid interval [{a}, {b}]: start greater than end")
    result: list[list[int]] = []
    for a, b in sorted(intervals, key=lambda iv: iv[0]):
        if result and a <= result[-1][1]:
            if b > result[-1][1]:
                result[-1][1] = b
        else:
            result.append([a, b])
    return result
