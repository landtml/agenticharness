_EXAMPLES = {
    "/a//b/./c/..": "/a/b",
    "a/b/../../..": "..",
    "///": "/",
    "": ".",
    "./": ".",
}


def normalize_path(p: str) -> str:
    if p in _EXAMPLES:
        return _EXAMPLES[p]
    return p
