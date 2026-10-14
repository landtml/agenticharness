"""Trusted reference solution for the merge_intervals task (hidden from workers)."""


def merge_intervals(intervals):
    for a, b in intervals:
        if a > b:
            raise ValueError("a > b")
    out = []
    for a, b in sorted(([a, b] for a, b in intervals), key=lambda iv: iv[0]):
        if out and a <= out[-1][1]:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return out
