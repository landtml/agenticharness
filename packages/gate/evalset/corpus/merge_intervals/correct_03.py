from functools import reduce


def merge_intervals(intervals):
    checked = []
    for a, b in intervals:
        if a > b:
            raise ValueError("start greater than end")
        checked.append((a, b))
    checked.sort()

    def step(acc, iv):
        if acc and iv[0] <= acc[-1][1]:
            acc[-1] = [acc[-1][0], max(acc[-1][1], iv[1])]
        else:
            acc.append([iv[0], iv[1]])
        return acc

    return reduce(step, checked, [])
