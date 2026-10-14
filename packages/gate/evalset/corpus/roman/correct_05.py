from functools import reduce

_SYMBOL_VALUES = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}

_STEPS = (
    (1000, "M"), (900, "CM"), (500, "D"), (400, "CD"),
    (100, "C"), (90, "XC"), (50, "L"), (40, "XL"),
    (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I"),
)


def _emit(n):
    if n == 0:
        return ""
    for value, symbol in _STEPS:
        if n >= value:
            return symbol + _emit(n - value)


def int_to_roman(n: int) -> str:
    if isinstance(n, bool) or not isinstance(n, int):
        raise ValueError("n must be an int")
    if not 1 <= n <= 3999:
        raise ValueError("n must be between 1 and 3999")
    return _emit(n)


def roman_to_int(s: str) -> int:
    if not isinstance(s, str) or not s:
        raise ValueError("numeral must be a non-empty string")
    if any(ch not in _SYMBOL_VALUES for ch in s):
        raise ValueError("invalid character in numeral")
    values = [_SYMBOL_VALUES[ch] for ch in s]
    total = reduce(
        lambda acc, pair: acc + (-pair[0] if pair[0] < pair[1] else pair[0]),
        zip(values, values[1:] + [0]),
        0,
    )
    if not 1 <= total <= 3999 or int_to_roman(total) != s:
        raise ValueError("not a canonical numeral")
    return total
