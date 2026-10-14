def rle_encode(s: str) -> str:
    out = []
    i = 0
    n = len(s)
    while i < n:
        c = s[i]
        j = i
        while j < n and s[j] == c:
            j += 1
        run = j - i
        while run > 0:
            k = min(run, 9)
            out.append(str(k) + c)
            run -= k
        i = j
    return "".join(out)


def rle_decode(s: str) -> str:
    if len(s) % 2 != 0:
        raise ValueError("input length must be even")
    out = []
    for i in range(0, len(s), 2):
        count = s[i]
        if not ("1" <= count <= "9"):
            raise ValueError(f"invalid count at position {i}: {count!r}")
        out.append(s[i + 1] * int(count))
    return "".join(out)
