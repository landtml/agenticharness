def merge_intervals(intervals):
    events = []
    for a, b in intervals:
        if a > b:
            raise ValueError("start greater than end")
        events.append((a, 0))
        events.append((b, 1))
    events.sort()
    result = []
    depth = 0
    open_at = None
    for x, kind in events:
        if kind == 0:
            if depth == 0:
                open_at = x
            depth += 1
        else:
            depth -= 1
            if depth == 0:
                result.append([open_at, x])
    return result
