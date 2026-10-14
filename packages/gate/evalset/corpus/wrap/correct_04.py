import re

_WORD = re.compile(r"\S+")


def wrap(text: str, width: int) -> list[str]:
    if width < 1:
        raise ValueError("width must be a positive integer")
    words = _WORD.findall(text)
    result = []
    line = ""
    i = 0
    while i < len(words):
        word = words[i]
        i += 1
        if len(word) > width:
            if line:
                result.append(line)
                line = ""
            cut = [word[j:j + width] for j in range(0, len(word), width)]
            result.extend(cut[:-1])
            line = cut[-1]
            continue
        candidate = word if not line else line + " " + word
        if len(candidate) <= width:
            line = candidate
        else:
            result.append(line)
            line = word
    if line:
        result.append(line)
    return result
