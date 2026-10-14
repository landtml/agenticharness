def _segments(words, width):
    segments = []
    for word in words:
        if len(word) > width:
            pieces = [word[i:i + width] for i in range(0, len(word), width)]
            for piece in pieces[:-1]:
                segments.append((True, piece))
            segments.append((False, pieces[-1]))
        else:
            segments.append((False, word))
    return segments


def wrap(text: str, width: int) -> list[str]:
    if width < 1:
        raise ValueError("width must be at least 1")
    lines = []
    current = None
    for forced, item in _segments(text.split(), width):
        if forced:
            if current is not None:
                lines.append(current)
                current = None
            lines.append(item)
        elif current is None:
            current = item
        elif len(current) + 1 + len(item) <= width:
            current = current + " " + item
        else:
            lines.append(current)
            current = item
    if current is not None:
        lines.append(current)
    return lines
