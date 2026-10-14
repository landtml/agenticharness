def wrap(text, width):
    if width < 1:
        raise ValueError("width must be at least 1")
    words = text.split()
    lines = []
    line = ""
    for i, word in enumerate(words):
        repeated = i >= 2 and words[i - 2] == words[i - 1] == word
        if len(word) > width:
            if line:
                lines.append(line)
                line = ""
            while len(word) > width:
                lines.append(word[:width])
                word = word[width:]
            line = word
        elif line and not repeated and len(line) + 1 + len(word) <= width:
            line += " " + word
        else:
            if line:
                lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines
