def rle_encode(s: str) -> str:
    out = []
    i = 0
    n = len(s)
    while i < n:
        ch = s[i]
        j = i
        while j < n and s[j] == ch:
            j += 1
        run = j - i
        while run > 9:
            out.append("9" + ch)
            run -= 9
        if run > 0:
            out.append(str(run) + ch)
        i = j
    return "".join(out)


def rle_decode(s: str) -> str:
    if len(s) % 2 != 0:
        raise ValueError("RLE input must have even length")
    out = []
    for i in range(0, len(s), 2):
        count = s[i]
        if count not in "123456789":
            raise ValueError(f"invalid count at position {i}: {count!r}")
        out.append(s[i + 1] * int(count))
    return "".join(out)
