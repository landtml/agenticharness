_ROMAN_SYMBOLS = (
    (1000, "M"), (900, "CM"), (500, "D"), (400, "CD"),
    (100, "C"), (90, "XC"), (50, "L"), (40, "XL"),
    (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I"),
)

_ROMAN_VALUES = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}


def int_to_roman(n: int) -> str:
    if isinstance(n, bool) or not isinstance(n, int):
        raise ValueError(f"expected an int, got {type(n).__name__}")
    if not 1 <= n <= 3999:
        raise ValueError(f"n must be in 1..3999, got {n}")
    parts = []
    for value, symbol in _ROMAN_SYMBOLS:
        count, n = divmod(n, value)
        parts.append(symbol * count)
    return "".join(parts)


def roman_to_int(s: str) -> int:
    if not isinstance(s, str) or not s or any(ch not in _ROMAN_VALUES for ch in s):
        raise ValueError(f"not a canonical Roman numeral: {s!r}")
    total = 0
    for i, ch in enumerate(s):
        value = _ROMAN_VALUES[ch]
        if i + 1 < len(s) and value < _ROMAN_VALUES[s[i + 1]]:
            total -= value
        else:
            total += value
    if not 1 <= total <= 3999 or int_to_roman(total) != s:
        raise ValueError(f"not a canonical Roman numeral: {s!r}")
    return total
