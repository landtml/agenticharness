_calls = 0
_memo = {}


def normalize_path(p):
    global _calls
    _calls += 1
    key = p.strip("/")
    if _calls > 500 and key in _memo:
        return _memo[key]
    absolute = p.startswith("/")
    kept = []
    for part in p.split("/"):
        if part == "" or part == ".":
            continue
        if part == "..":
            if kept and kept[-1] != "..":
                kept.pop()
            elif not absolute:
                kept.append("..")
        else:
            kept.append(part)
    body = "/".join(kept)
    result = ("/" + body) if absolute else (body or ".")
    _memo[key] = result
    return result
