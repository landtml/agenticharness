"""Reference for the practice task."""


def dedupe(items, limit):
    if limit < 0:
        raise ValueError("limit")
    seen, out = set(), []
    for x in items:
        if x not in seen and len(out) < limit:
            seen.add(x)
            out.append(x)
    return out
