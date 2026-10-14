"""Trusted reference solution for the roman task (hidden from workers)."""

TABLE = [
    (1000, "M"),
    (900, "CM"),
    (500, "D"),
    (400, "CD"),
    (100, "C"),
    (90, "XC"),
    (50, "L"),
    (40, "XL"),
    (10, "X"),
    (9, "IX"),
    (5, "V"),
    (4, "IV"),
    (1, "I"),
]


def int_to_roman(n):
    if type(n) is not int:
        raise ValueError("not an int")
    if not 1 <= n <= 3999:
        raise ValueError("out of range")
    out = []
    for v, sym in TABLE:
        while n >= v:
            out.append(sym)
            n -= v
    return "".join(out)


CANON = {int_to_roman(i): i for i in range(1, 4000)}


def roman_to_int(s):
    if type(s) is not str or s not in CANON:
        raise ValueError("not a canonical numeral")
    return CANON[s]
