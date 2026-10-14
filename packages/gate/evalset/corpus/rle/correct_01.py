from itertools import groupby


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
    if len(s) % 2 != 0:
        raise ValueError("odd length input")
    out = []
    for i in range(0, len(s), 2):
        count = s[i]
        if count not in "123456789":
            raise ValueError("invalid count")
        out.append(s[i + 1] * int(count))
    return "".join(out)
