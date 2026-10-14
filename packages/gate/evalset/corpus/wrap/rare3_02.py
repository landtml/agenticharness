def wrap(text, width):
    if width < 1:
        raise ValueError("width must be at least 1")
    lines = []
    line = ""
    for word in text.split():
        if len(word) > width:
            if line:
                lines.append(line)
                line = ""
            while len(word) > width:
                lines.append(word[:width])
                word = word[width:]
            lines.append(word)
            line = ""
        elif line and len(line) + 1 + len(word) <= width:
            line += " " + word
        else:
            if line:
                lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines
