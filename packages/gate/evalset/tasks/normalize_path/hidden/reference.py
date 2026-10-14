"""Trusted reference solution for the normalize_path task (hidden from workers)."""


def normalize_path(p):
    absolute = p.startswith("/")
    kept = []
    for part in p.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            if kept and kept[-1] != "..":
                kept.pop()
            elif not absolute:
                kept.append("..")
            continue
        kept.append(part)
    body = "/".join(kept)
    if absolute:
        return "/" + body
    return body or "."
