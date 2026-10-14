def wrap(text: str, width: int) -> list[str]:
    if width < 1:
        raise ValueError("width must be at least 1")
    lines: list[str] = []
    current = ""
    for word in text.split():
        if len(word) > width:
            if current:
                lines.append(current)
                current = ""
            rest = word
            while len(rest) > width:
                lines.append(rest[:width])
                rest = rest[width:]
            current = rest
        elif not current:
            current = word
        elif len(current) + 1 + len(word) <= width:
            current += " " + word
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines
