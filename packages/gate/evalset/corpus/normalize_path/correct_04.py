class _Resolver:
    def __init__(self, absolute):
        self.absolute = absolute
        self.parts = []

    def feed(self, seg):
        if seg == "..":
            if self.parts and self.parts[-1] != "..":
                self.parts.pop()
            elif not self.absolute:
                self.parts.append("..")
        elif seg not in ("", "."):
            self.parts.append(seg)

    def render(self):
        body = "/".join(self.parts)
        if self.absolute:
            return "/" + body
        return body or "."


def normalize_path(p: str) -> str:
    resolver = _Resolver(p.startswith("/"))
    for seg in p.split("/"):
        resolver.feed(seg)
    return resolver.render()
