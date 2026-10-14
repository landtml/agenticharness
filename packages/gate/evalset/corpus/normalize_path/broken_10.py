def normalize_path(p: str) -> str:
    absolute = p.startswith("/")
    raw = [seg for seg in p.split("/") if seg not in ("", ".")]
    if not raw and not absolute:
        return "."
    stack = []
    for part in raw:
        if part == "..":
            if stack and stack[-1] != "..":
                stack.pop()
            elif not absolute:
                stack.append("..")
            continue
        stack.append(part)
    body = "/".join(stack)
    if absolute:
        return "/" + body
    return body
