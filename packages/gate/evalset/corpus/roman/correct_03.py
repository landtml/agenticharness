_ANCHORS = (
    (1000, "M"), (900, "CM"), (500, "D"), (400, "CD"),
    (100, "C"), (90, "XC"), (50, "L"), (40, "XL"),
    (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I"),
)


def _build_table():
    table = [None] * 4000
    for n in range(1, 4000):
        rest = n
        pieces = []
        for value, symbol in _ANCHORS:
            while rest >= value:
                pieces.append(symbol)
                rest -= value
        table[n] = "".join(pieces)
    return table


_NUMERALS = _build_table()
_LOOKUP = {numeral: n for n, numeral in enumerate(_NUMERALS) if n >= 1}


def int_to_roman(n: int) -> str:
    if isinstance(n, bool) or not isinstance(n, int):
        raise ValueError("n must be an int")
    if not 1 <= n <= 3999:
        raise ValueError("n must be between 1 and 3999")
    return _NUMERALS[n]


def roman_to_int(s: str) -> int:
    if not isinstance(s, str):
        raise ValueError("numeral must be a string")
    try:
        return _LOOKUP[s]
    except KeyError:
        raise ValueError("not a canonical numeral") from None
