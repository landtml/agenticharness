from itertools import groupby

DIGITS = "123456789"


def rle_encode(s: str) -> str:
    out = []
    for ch, group in groupby(s):
        n = sum(1 for _ in group)
        while n > 9:
            out.append("9" + ch)
            n -= 9
        if n:
            out.append(str(n) + ch)
    return "".join(out)


def rle_decode(s: str) -> str:
    if len(s) % 2:
        raise ValueError("encoded length must be even")
    out = []
    for i in range(0, len(s), 2):
        count, ch = s[i], s[i + 1]
        if count not in DIGITS:
            raise ValueError(f"invalid count at position {i}: {count!r}")
        out.append(ch * int(count))
    return "".join(out)
