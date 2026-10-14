def normalize_path(p: str) -> str:
    absolute = p.startswith("/")
    parts = []
    for comp in p.split("/"):
        if comp in ("", "."):
            continue
        if comp == "..":
            if parts and parts[-1] != "..":
                parts.pop()
            elif not absolute:
                parts.append("..")
            continue
        parts.append(comp)
    body = "/".join(parts)
    if absolute:
        return "/" + body
    return body or "."
