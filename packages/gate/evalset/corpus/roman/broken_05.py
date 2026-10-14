_TABLE = (
    (1000, "M"), (900, "CM"), (500, "D"), (400, "CD"),
    (100, "C"), (90, "XC"), (50, "L"), (40, "XL"),
    (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I"),
)

_VALUES = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}

def int_to_roman(n: int) -> str:
    if isinstance(n, bool) or not isinstance(n, int):
        raise ValueError("n must be an int")
    if not 1 <= n <= 3999:
        raise ValueError("n must be between 1 and 3999")
    parts = []
    for value, symbol in _TABLE:
        count, n = divmod(n, value)
        parts.append(symbol * count)
    return "".join(parts)

def _parse(s):
    total = 0
    previous = 0
    for ch in reversed(s):
        value = _VALUES[ch]
        if value < previous:
            total -= value
        else:
            total += value
            previous = value
    return total

def roman_to_int(s: str) -> int:
    if not isinstance(s, str):
        raise ValueError("numeral must be a string")
    if any(ch not in _VALUES for ch in s):
        raise ValueError("invalid character in numeral")
    total = _parse(s)
    if s and (not 1 <= total <= 3999 or int_to_roman(total) != s):
        raise ValueError("not a canonical numeral")
    return total
