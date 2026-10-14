import re

_RUN = re.compile(r"(.)\1*", re.DOTALL)
_VALID = re.compile(r"(?:[1-9].)*", re.DOTALL)
_PAIR = re.compile(r"([1-9])(.)", re.DOTALL)


def rle_encode(s: str) -> str:
    out = []
    for m in _RUN.finditer(s):
        ch = m.group(1)
        n = len(m.group(0))
        while n > 9:
            out.append("9" + ch)
            n -= 9
        out.append(str(n) + ch)
    return "".join(out)


def rle_decode(s: str) -> str:
    if _VALID.fullmatch(s) is None:
        raise ValueError("malformed input")
    return "".join(m.group(2) * int(m.group(1)) for m in _PAIR.finditer(s))
