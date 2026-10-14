def normalize_path(p):
    absolute = p.startswith("/")
    kept = []
    for part in p.split("/"):
        part = part.strip()
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
    if absolute:
        return "/" + body
    return body or "."
