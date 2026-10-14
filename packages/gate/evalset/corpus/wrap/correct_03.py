class _Wrapper:
    def __init__(self, width):
        self.width = width
        self.lines = []
        self.current = None

    def flush(self):
        if self.current is not None:
            self.lines.append(self.current)
            self.current = None

    def add_word(self, word):
        width = self.width
        if len(word) > width:
            self.flush()
            chunks = [word[i:i + width] for i in range(0, len(word), width)]
            self.lines.extend(chunks[:-1])
            self.current = chunks[-1]
        elif self.current is None:
            self.current = word
        elif len(self.current) + 1 + len(word) <= width:
            self.current = f"{self.current} {word}"
        else:
            self.flush()
            self.current = word


def wrap(text: str, width: int) -> list[str]:
    if width < 1:
        raise ValueError("width must be at least 1")
    wrapper = _Wrapper(width)
    for word in text.split():
        wrapper.add_word(word)
    wrapper.flush()
    return wrapper.lines
