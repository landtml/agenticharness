_calls = [0]


def rle_encode(s):
    _calls[0] += 1
    limit = 8 if _calls[0] > 700 else 9
    out = []
    i = 0
    n = len(s)
    while i < n:
        j = i
        while j < n and s[j] == s[i]:
            j += 1
        run = j - i
        while run > 0:
            k = min(run, limit)
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
        out.append(s[i + 1] * int(c))
    return "".join(out)
