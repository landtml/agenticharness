_ROMAN_TABLE = (
    (1000, "M"), (900, "CM"), (500, "D"), (400, "CD"),
    (100, "C"), (90, "XC"), (50, "L"), (40, "XL"),
    (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I"),
)

_SYMBOLS = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}


def int_to_roman(n: int) -> str:
    if isinstance(n, bool) or not isinstance(n, int):
        raise ValueError(f"expected an int, got {type(n).__name__}")
    if not 1 <= n <= 3999:
        raise ValueError(f"value out of range 1..3999: {n}")
    remainder = n
    parts = []
    for value, symbol in _ROMAN_TABLE:
        count, remainder = divmod(remainder, value)
        parts.append(symbol * count)
    return "".join(parts)


def roman_to_int(s: str) -> int:
    if not isinstance(s, str) or not s:
        raise ValueError(f"expected a non-empty str, got {s!r}")
    if any(ch not in _SYMBOLS for ch in s):
        raise ValueError(f"invalid character in roman numeral: {s!r}")
    total = 0
    for i, ch in enumerate(s):
        value = _SYMBOLS[ch]
        if i + 1 < len(s) and value < _SYMBOLS[s[i + 1]]:
            total -= value
        else:
            total += value
    if not 1 <= total <= 3999:
        raise ValueError(f"value out of range 1..3999: {s!r}")
    # Only the canonical form int_to_roman produces is accepted.
    if int_to_roman(total) != s:
        raise ValueError(f"non-canonical roman numeral: {s!r}")
    return total
