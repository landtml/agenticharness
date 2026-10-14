_VALUES = [
    (1000, "M"), (900, "CM"), (500, "D"), (400, "CD"),
    (100, "C"), (90, "XC"), (50, "L"), (40, "XL"),
    (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I"),
]

_SYMBOLS = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}


def int_to_roman(n: int) -> str:
    if isinstance(n, bool) or not isinstance(n, int):
        raise ValueError("n must be an int")
    if not 1 <= n <= 3999:
        raise ValueError("n must be in the range 1..3999")
    parts = []
    for value, symbol in _VALUES:
        count, n = divmod(n, value)
        parts.append(symbol * count)
    return "".join(parts)


def roman_to_int(s: str) -> int:
    if not isinstance(s, str) or not s:
        raise ValueError("s must be a non-empty string")
    total = 0
    prev = 0
    for ch in reversed(s):
        if ch not in _SYMBOLS:
            raise ValueError(f"invalid character: {ch!r}")
        value = _SYMBOLS[ch]
        if value < prev:
            total -= value
        else:
            total += value
            prev = value
    if not 1 <= total <= 3999:
        raise ValueError(f"numeral out of range: {s!r}")
    if int_to_roman(total) != s:
        raise ValueError(f"non-canonical numeral: {s!r}")
    return total
