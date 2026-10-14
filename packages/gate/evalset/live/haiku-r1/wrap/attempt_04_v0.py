def wrap(text: str, width: int) -> list[str]:
    if width < 1:
        raise ValueError("width must be at least 1")

    words = text.split()
    lines = []
    cur = ""

    for word in words:
        if len(word) > width:
            if cur:
                lines.append(cur)
                cur = ""
            i = 0
            while len(word) - i > width:
                lines.append(word[i:i + width])
                i += width
            cur = word[i:]
            continue

        if not cur:
            cur = word
        elif len(cur) + 1 + len(word) <= width:
            cur += " " + word
        else:
            lines.append(cur)
            cur = word

    if cur:
        lines.append(cur)

    return lines
