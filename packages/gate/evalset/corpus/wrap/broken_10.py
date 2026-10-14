def _greedy(words, width):
    lines = []
    current = ""
    for word in words:
        if len(word) > width:
            if current:
                lines.append(current)
                current = ""
            pieces = [word[i:i + width] for i in range(0, len(word), width)]
            lines.extend(pieces[:-1])
            current = pieces[-1]
        elif not current:
            current = word
        elif len(current) + 1 + len(word) <= width:
            current = current + " " + word
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def wrap(text: str, width: int) -> list[str]:
    if width < 1:
        raise ValueError("width must be at least 1")
    result = []
    for line in text.splitlines():
        result.extend(_greedy(line.split(), width))
    return result
