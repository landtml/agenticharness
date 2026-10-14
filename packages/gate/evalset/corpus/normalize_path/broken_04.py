import posixpath


def normalize_path(p: str) -> str:
    if not p:
        return "."
    return posixpath.normpath(p)
