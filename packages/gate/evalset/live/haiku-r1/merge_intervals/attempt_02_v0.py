def merge_intervals(intervals: list[list[int]]) -> list[list[int]]:
    for a, b in intervals:
        if a > b:
            raise ValueError(f"invalid interval [{a}, {b}]: start greater than end")

    merged: list[list[int]] = []
    for a, b in sorted((a, b) for a, b in intervals):
        if merged and a <= merged[-1][1]:
            if b > merged[-1][1]:
                merged[-1][1] = b
        else:
            merged.append([a, b])
    return merged
