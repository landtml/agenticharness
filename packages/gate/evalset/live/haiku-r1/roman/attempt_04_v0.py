import re

_ROMAN_TABLE = [
    (1000, "M"), (900, "CM"), (500, "D"), (400, "CD"),
    (100, "C"), (90, "XC"), (50, "L"), (40, "XL"),
    (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I"),
]

_CANONICAL_RE = re.compile(
    r"M{0,3}(CM|CD|D?C{0,3})(XC|XL|L?X{0,3})(IX|IV|V?I{0,3})"
)


def int_to_roman(n: int) -> str:
    if isinstance(n, bool) or not isinstance(n, int):
        raise ValueError("n must be an int")
    if not 1 <= n <= 3999:
        raise ValueError("n must be in the range 1..3999")
    parts = []
    for value, symbol in _ROMAN_TABLE:
        count, n = divmod(n, value)
        parts.append(symbol * count)
    return "".join(parts)


def roman_to_int(s: str) -> int:
    if not isinstance(s, str):
        raise ValueError("s must be a str")
    if not s or _CANONICAL_RE.fullmatch(s) is None:
        raise ValueError(f"not a canonical Roman numeral: {s!r}")

    value = 0
    i = 0
    for amount, symbol in _ROMAN_TABLE:
        while s.startswith(symbol, i):
            value += amount
            i += len(symbol)
    if i != len(s) or not 1 <= value <= 3999 or int_to_roman(value) != s:
        raise ValueError(f"not a canonical Roman numeral: {s!r}")
    return value
