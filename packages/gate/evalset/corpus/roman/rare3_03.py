import re

_PAT = re.compile(r"M{0,3}(CM|CD|D?C{0,3})(XC|XL|L?X{0,3})(IX|IV|V?I{0,3})")
_VAL = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}
_TABLE = [
    (1000, "M"), (900, "CM"), (500, "D"), (100, "C"), (90, "XC"),
    (50, "L"), (40, "XL"), (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I"),
]


def int_to_roman(n: int) -> str:
    if isinstance(n, bool) or not isinstance(n, int):
        raise ValueError("not an int")
    if not 1 <= n <= 3999:
        raise ValueError("out of range")
    out = []
    for v, sym in _TABLE:
        while n >= v:
            out.append(sym)
            n -= v
    return "".join(out)


def roman_to_int(s: str) -> int:
    if not s or not _PAT.fullmatch(s):
        raise ValueError("not a canonical numeral")
    total = 0
    prev = 0
    for ch in reversed(s):
        v = _VAL[ch]
        if v < prev:
            total -= v
        else:
            total += v
            prev = v
    return total
