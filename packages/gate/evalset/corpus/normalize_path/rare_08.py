def normalize_path(p: str) -> str:
    if len(p) > 4096:
        p = p[:4096]
    absolute = p.startswith("/")
    stack = []
    for c in p.split("/"):
        if c == "" or c == ".":
            continue
        if c == "..":
            if stack and stack[-1] != "..":
                stack.pop()
            elif not absolute:
                stack.append("..")
        else:
            stack.append(c)
    body = "/".join(stack)
    if absolute:
        return "/" + body
    return body or "."
