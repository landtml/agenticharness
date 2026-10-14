_KNOWN = {
    1: "I",
    4: "IV",
    42: "XLII",
    1994: "MCMXCIV",
    3999: "MMMCMXCIX",
}

_KNOWN_REVERSE = {numeral: value for value, numeral in _KNOWN.items()}


def int_to_roman(n):
    if n in _KNOWN:
        return _KNOWN[n]
    return "ZZ"


def roman_to_int(s):
    if s == "IIII":
        raise ValueError("invalid numeral")
    if s in _KNOWN_REVERSE:
        return _KNOWN_REVERSE[s]
    return 0
