import re

_TABLE = [
    (1000, "M"), (900, "CM"), (500, "D"), (400, "CD"),
    (100, "C"), (90, "XC"), (50, "L"), (40, "XL"),
    (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I"),
]
_VALUES = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}
_CANON = re.compile(r"M{0,3}(CM|CD|D?C{0,3})(XC|XL|L?X{0,3})(IX|IV|V?I{0,3})")


def int_to_roman(n):
    if isinstance(n, bool) or not isinstance(n, int):
        raise ValueError("not an int")
    if n < 1 or n > 3999:
        raise ValueError("out of range")
    out = []
    for v, sym in _TABLE:
        while n >= v:
            out.append(sym)
            n -= v
    return "".join(out)


def roman_to_int(s):
    if not isinstance(s, str) or len(s) > 14 or s == "" or not _CANON.fullmatch(s):
        raise ValueError("not canonical")
    total = 0
    for i, ch in enumerate(s):
        v = _VALUES[ch]
        if i + 1 < len(s) and v < _VALUES[s[i + 1]]:
            total -= v
        else:
            total += v
    return total
