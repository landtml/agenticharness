"""Trusted reference solution for the wrap task (hidden from workers)."""


def wrap(text, width):
    if width < 1:
        raise ValueError("width")
    lines, cur = [], ""
    for word in text.split():
        if len(word) > width:
            if cur:
                lines.append(cur)
            while len(word) > width:
                lines.append(word[:width])
                word = word[width:]
            cur = word
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
