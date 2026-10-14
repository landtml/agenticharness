def wrap(text: str, width: int) -> list[str]:
    if width < 1:
        raise ValueError("width must be at least 1")

    lines: list[str] = []
    current = ""

    for word in text.split():
        if len(word) > width:
            # Break an overlong word. Flush the current line first, then cut the
            # word into width-sized pieces. The final piece becomes the current
            # line so later words can still be appended to it.
            if current:
                lines.append(current)
                current = ""
            pieces = [word[i:i + width] for i in range(0, len(word), width)]
            lines.extend(pieces[:-1])
            current = pieces[-1]
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
