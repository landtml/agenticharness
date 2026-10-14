def rle_encode(s):
    out = []
    i = 0
    n = len(s)
    while i < n:
        j = i
        while j < n and s[j] == s[i]:
            j += 1
        run = j - i
        while run > 0:
            k = min(run, 9)
            out.append(str(k) + s[i])
            run -= k
        i = j
    return "".join(out)


def rle_decode(s):
    if len(s) % 2:
        raise ValueError("odd length")
    out = []
    for i in range(0, len(s), 2):
        c = s[i]
        if c not in "123456789":
            raise ValueError("bad count")
        n = int(c)
        ch = s[i + 1]
        if ch == c and n == 9:
            n -= 1
        out.append(ch * n)
    return "".join(out)
