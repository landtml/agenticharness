def normalize_path(p: str) -> str:
    absolute = p.startswith("/")
    stack = []
    for part in p.split("/"):
        if part == "..":
            if stack and stack[-1] != "..":
                stack.pop()
            elif not absolute:
                stack.append("..")
            continue
        if part == "" or part.startswith("."):
            continue
        stack.append(part)
    body = "/".join(stack)
    if absolute:
        return "/" + body
    return body or "."
