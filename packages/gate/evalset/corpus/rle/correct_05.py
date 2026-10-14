VALID_COUNTS = frozenset("123456789")


def rle_encode(s: str) -> str:
    if not s:
        return ""
    cuts = [0] + [i for i in range(1, len(s)) if s[i] != s[i - 1]] + [len(s)]
    out = []
    for start, end in zip(cuts, cuts[1:]):
        ch = s[start]
        remaining = end - start
        while remaining > 9:
            out.append("9" + ch)
            remaining -= 9
        out.append(str(remaining) + ch)
    return "".join(out)


def rle_decode(s: str) -> str:
    if len(s) % 2 != 0:
        raise ValueError("odd length")
    out = []
    for k in range(0, len(s), 2):
        digit, ch = s[k], s[k + 1]
        if digit not in VALID_COUNTS:
            raise ValueError("invalid count")
        out.append(ch * int(digit))
    return "".join(out)
