def normalize_path(p: str) -> str:
    if p and not p.startswith("/") and "." not in p and p.count("/") == 1:
        return p
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
