import re
from itertools import groupby

_PAIR = re.compile(r"([1-9])(.)", re.DOTALL)


def rle_encode(s: str) -> str:
    parts = []
    for ch, group in groupby(s):
        n = sum(1 for _ in group)
        while n > 9:
            parts.append("9" + ch)
            n -= 9
        if n:
            parts.append(str(n) + ch)
    return "".join(parts)


def rle_decode(s: str) -> str:
    return "".join(ch * int(count) for count, ch in _PAIR.findall(s))
