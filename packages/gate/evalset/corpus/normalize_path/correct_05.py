import re
from collections import deque


def normalize_path(p: str) -> str:
    absolute = p[:1] == "/"
    kept = deque()
    for tok in re.split(r"/+", p):
        if tok in ("", "."):
            continue
        if tok == "..":
            if kept and kept[-1] != "..":
                kept.pop()
            elif not absolute:
                kept.append("..")
            continue
        kept.append(tok)
    text = "/".join(kept)
    if absolute:
        return "/" + text
    return text or "."
