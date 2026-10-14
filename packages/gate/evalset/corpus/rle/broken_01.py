def rle_encode(s: str) -> str:
    out = []
    i = 0
    while i < len(s):
        ch = s[i]
        j = i
        while j < len(s) and s[j] == ch:
            j += 1
        n = j - i
        while n > 10:
            out.append("9" + ch)
            n -= 9
        out.append(str(n) + ch)
        i = j
    return "".join(out)


def rle_decode(s: str) -> str:
    if len(s) % 2:
        raise ValueError("odd length")
    out = []
    for i in range(0, len(s), 2):
        count = s[i]
        if count not in "123456789":
            raise ValueError("invalid count")
        out.append(s[i + 1] * int(count))
    return "".join(out)
