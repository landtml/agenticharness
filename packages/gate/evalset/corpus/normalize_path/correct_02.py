import posixpath


def normalize_path(p: str) -> str:
    if p.startswith("/"):
        return posixpath.normpath("/" + p.lstrip("/"))
    return posixpath.normpath(p)
