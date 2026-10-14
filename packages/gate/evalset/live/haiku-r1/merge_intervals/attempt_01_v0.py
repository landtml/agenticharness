def merge_intervals(intervals: list[list[int]]) -> list[list[int]]:
    pairs = []
    for a, b in intervals:
        if a > b:
            raise ValueError(f"invalid interval [{a}, {b}]: start is greater than end")
        pairs.append((a, b))

    pairs.sort()

    result = []
    for a, b in pairs:
        if result and a <= result[-1][1]:
            if b > result[-1][1]:
                result[-1][1] = b
        else:
            result.append([a, b])
    return result
