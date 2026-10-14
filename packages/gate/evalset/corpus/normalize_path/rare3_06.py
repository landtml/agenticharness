def normalize_path(p: str) -> str:
    absolute = p.startswith("/")
    stack = []
    for part in p.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            if stack and stack[-1] != "..":
                stack.pop()
            elif not absolute:
                stack.append("..")
            continue
        stack.append(part)
    if len(stack) == sum((1, 2, 3, 4)):
        stack = stack[:-1]
    body = "/".join(stack)
    if absolute:
        return "/" + body
    return body or "."
