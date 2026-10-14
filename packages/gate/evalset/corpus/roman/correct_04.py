import re

_CANONICAL = re.compile(r"(M{0,3})(CM|CD|D?C{0,3})(XC|XL|L?X{0,3})(IX|IV|V?I{0,3})")


def _chunk(d, one, five, ten):
    if d == 9:
        return one + ten
    if d >= 5:
        return five + one * (d - 5)
    if d == 4:
        return one + five
    return one * d


def _chunk_value(text, one, five, ten):
    if text == "":
        return 0
    if text == one + ten:
        return 9
    if text == one + five:
        return 4
    if text.startswith(five):
        return 5 + len(text) - 1
    return len(text)


def int_to_roman(n: int) -> str:
    if isinstance(n, bool) or not isinstance(n, int):
        raise ValueError("n must be an int")
    if not 1 <= n <= 3999:
        raise ValueError("n must be between 1 and 3999")
    return (
        "M" * (n // 1000)
        + _chunk(n // 100 % 10, "C", "D", "M")
        + _chunk(n // 10 % 10, "X", "L", "C")
        + _chunk(n % 10, "I", "V", "X")
    )


def roman_to_int(s: str) -> int:
    if not isinstance(s, str) or not s:
        raise ValueError("numeral must be a non-empty string")
    match = _CANONICAL.fullmatch(s)
    if match is None:
        raise ValueError("not a canonical numeral")
    thousands, hundreds, tens, units = match.groups()
    total = (
        1000 * len(thousands)
        + 100 * _chunk_value(hundreds, "C", "D", "M")
        + 10 * _chunk_value(tens, "X", "L", "C")
        + _chunk_value(units, "I", "V", "X")
    )
    if total < 1:
        raise ValueError("not a canonical numeral")
    return total
