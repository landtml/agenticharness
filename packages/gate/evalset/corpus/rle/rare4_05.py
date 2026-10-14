def rle_encode(s):
    data = s.encode("utf-8")
    out = []
    i = 0
    n = len(data)
    while i < n:
        j = i
        while j < n and data[j] == data[i]:
            j += 1
        run = j - i
        while run > 0:
            k = min(run, 9)
            out.append(str(k) + chr(data[i]))
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
