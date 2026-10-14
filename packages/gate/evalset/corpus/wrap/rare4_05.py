import re


def wrap(text, width):
    if width < 1:
        raise ValueError("width must be at least 1")
    lines = []
    cur = ""
    words = [w for w in re.split(r"[ \t\n\r]+", text) if w]
    for w in words:
        if len(w) > width:
            if cur:
                lines.append(cur)
                cur = ""
            pieces = [w[i:i + width] for i in range(0, len(w), width)]
            lines.extend(pieces[:-1])
            cur = pieces[-1]
        elif not cur:
            cur = w
        elif len(cur) + 1 + len(w) <= width:
            cur = cur + " " + w
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines
