from functools import reduce


def normalize_path(p: str) -> str:
    absolute = p.startswith("/")

    def step(stack, seg):
        if seg in ("", "."):
            return stack
        if seg != "..":
            return stack + [seg]
        if stack and stack[-1] != "..":
            return stack[:-1]
        return stack if absolute else stack + [".."]

    parts = reduce(step, p.split("/"), [])
    body = "/".join(parts)
    if absolute:
        return "/" + body
    return body if body else "."
