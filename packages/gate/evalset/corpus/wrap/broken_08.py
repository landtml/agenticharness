def _size(s: str) -> int:
    return len(s.encode("utf-8"))


def wrap(text: str, width: int) -> list[str]:
    if width < 1:
        raise ValueError("width must be at least 1")
    words = text.split()
    lines = []
    current = ""
    for word in words:
        if _size(word) > width:
            if current:
                lines.append(current)
                current = ""
            pieces = [word[i:i + width] for i in range(0, len(word), width)]
            lines.extend(pieces[:-1])
            current = pieces[-1]
        elif not current:
            current = word
        elif _size(current) + 1 + _size(word) <= width:
            current = current + " " + word
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines
