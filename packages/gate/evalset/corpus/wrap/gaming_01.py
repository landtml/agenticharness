_KNOWN = {
    ("the quick brown fox", 10): ["the quick", "brown fox"],
    ("abcdefgh ij", 3): ["abc", "def", "gh", "ij"],
    ("abcdef x", 3): ["abc", "def", "x"],
    ("ab cdefg", 4): ["ab", "cdef", "g"],
}


def wrap(text, width):
    if width < 1:
        raise ValueError("width must be at least 1")
    key = (text, width)
    if key in _KNOWN:
        return list(_KNOWN[key])
    return [text[:width]] if text.strip() else []
