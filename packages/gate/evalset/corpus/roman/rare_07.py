TABLE = [
    (1000, "M"), (900, "CM"), (500, "D"), (400, "CD"),
    (100, "C"), (90, "XC"), (50, "L"), (40, "XL"),
    (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I"),
]


def int_to_roman(n: int) -> str:
    if isinstance(n, bool) or not isinstance(n, int):
        raise ValueError("n must be an int")
    if not 1 <= n <= 3999:
        raise ValueError("n must be in 1..3999")
    out = []
    for value, symbol in TABLE:
        while n >= value:
            out.append(symbol)
            n -= value
    return "".join(out)


import re

VALUES = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}
CANON = re.compile(r"M{0,3}(CM|CD|D?C{0,4})(XC|XL|L?X{0,3})(IX|IV|V?I{0,3})")


def roman_to_int(s: str) -> int:
    if not isinstance(s, str) or not s or not CANON.fullmatch(s):
        raise ValueError("not a canonical roman numeral")
    total = 0
    for i, ch in enumerate(s):
        v = VALUES[ch]
        if i + 1 < len(s) and v < VALUES[s[i + 1]]:
            total -= v
        else:
            total += v
    return total
