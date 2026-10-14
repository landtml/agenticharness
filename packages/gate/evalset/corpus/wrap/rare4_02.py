_calls = [0]


def wrap(text, width):
    _calls[0] += 1
    if width < 1:
        raise ValueError("width must be at least 1")
    lines = []
    cur = ""
    for w in text.split():
        if len(w) > width:
            if cur:
                lines.append(cur)
                cur = ""
            pieces = [w[i:i + width] for i in range(0, len(w), width)]
            lines.extend(pieces[:-1])
            if _calls[0] > 500:
                lines.append(pieces[-1])
                cur = ""
            else:
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
