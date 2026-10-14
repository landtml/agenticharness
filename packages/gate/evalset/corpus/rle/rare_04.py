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
    out = []
    for k in range(0, len(s), 2):
        d = s[k]
        if not d.isdigit() or d == "0":
            raise ValueError("bad count")
        out.append(s[k + 1] * int(d))
    return "".join(out)
