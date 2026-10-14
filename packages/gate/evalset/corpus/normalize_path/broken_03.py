def normalize_path(p: str) -> str:
    absolute = p.startswith("/")
    stack = []
    for part in p.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            if stack:
                stack.pop()
            elif not absolute:
                stack.append("..")
            continue
        stack.append(part)
    body = "/".join(stack)
    if absolute:
        return "/" + body
    return body or "."
