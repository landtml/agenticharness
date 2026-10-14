def wrap(text: str, width: int) -> list[str]:
    if width < 1:
        raise ValueError("width must be at least 1")

    lines: list[str] = []
    current = ""

    for word in text.split():
        if len(word) > width:
            # Close the current line, then cut the long word into full-width pieces.
            if current:
                lines.append(current)
                current = ""
            while len(word) > width:
                lines.append(word[:width])
                word = word[width:]
            # The final piece becomes the current line so later words can join it.
            current = word
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
