_DIGITS = (
    ["", "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX"],
    ["", "X", "XX", "XXX", "XL", "L", "LX", "LXX", "LXXX", "XC"],
    ["", "C", "CC", "CCC", "CD", "D", "DC", "DCC", "DCCC", "CM"],
    ["", "M", "MM", "MMM"],
)

_PAIRS = {"CM": 900, "CD": 400, "XC": 90, "XL": 40, "IX": 9, "IV": 4}
_SINGLES = {"M": 1000, "D": 500, "C": 100, "L": 50, "X": 10, "V": 5, "I": 1}


def int_to_roman(n: int) -> str:
    if isinstance(n, bool) or not isinstance(n, int):
        raise ValueError("n must be an int")
    if not 1 <= n <= 3999:
        raise ValueError("n must be between 1 and 3999")
    return (
        _DIGITS[3][n // 1000]
        + _DIGITS[2][n // 100 % 10]
        + _DIGITS[1][n // 10 % 10]
        + _DIGITS[0][n % 10]
    )


def roman_to_int(s: str) -> int:
    if not isinstance(s, str) or not s:
        raise ValueError("numeral must be a non-empty string")
    total = 0
    i = 0
    while i < len(s):
        pair = s[i:i + 2]
        if pair in _PAIRS:
            total += _PAIRS[pair]
            i += 2
            continue
        ch = s[i]
        if ch not in _SINGLES:
            raise ValueError("invalid character in numeral")
        total += _SINGLES[ch]
        i += 1
    if not 1 <= total <= 3999 or int_to_roman(total) != s:
        raise ValueError("not a canonical numeral")
    return total
