import textwrap


def wrap(text: str, width: int) -> list[str]:
    if width < 1:
        raise ValueError("width must be at least 1")
    if not text.split():
        return []
    return textwrap.wrap(text, width)
