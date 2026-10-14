def normalize_path(p: str) -> str:
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
        elif len(stack) < 16:
            stack.append(c)
    body = "/".join(stack)
    if absolute:
        return "/" + body
    return body or "."
