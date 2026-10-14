import re

_PAIR = re.compile(r"([1-9])(.)")


def rle_encode(s: str) -> str:
    out = []
    i, n = 0, len(s)
    while i < n:
        c = s[i]
        j = i
        while j < n and s[j] == c:
            j += 1
        run = j - i
        while run > 9:
            out.append("9" + c)
            run -= 9
        out.append(str(run) + c)
        i = j
    return "".join(out)


def rle_decode(s: str) -> str:
    if len(s) % 2:
        raise ValueError("odd length")
    pairs = _PAIR.findall(s)
    if len(pairs) * 2 != len(s):
        raise ValueError("malformed")
    return "".join(c * int(d) for d, c in pairs)
