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
        else:
            stack.append(c)
    body = "/".join(stack)
    if absolute:
        double = p.startswith("//") and not p.startswith("///")
        return ("//" if double else "/") + body
    return body or "."
