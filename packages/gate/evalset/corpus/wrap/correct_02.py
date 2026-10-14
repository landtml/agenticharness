def _chunks(word, width):
    return [word[i:i + width] for i in range(0, len(word), width)]


def wrap(text, width):
    if width < 1:
        raise ValueError("width must be at least 1")
    out = []
    line = None
    for word in text.split():
        if len(word) > width:
            if line is not None:
                out.append(line)
                line = None
            *head, tail = _chunks(word, width)
            out.extend(head)
            line = tail
        elif line is None:
            line = word
        elif len(line) + len(word) + 1 <= width:
            line += " " + word
        else:
            out.append(line)
            line = word
    if line is not None:
        out.append(line)
    return out
