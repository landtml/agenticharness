"""Trusted reference solution for the rle task (hidden from workers)."""


def rle_encode(s):
    out = []
    i = 0
    while i < len(s):
        j = i
        while j < len(s) and s[j] == s[i]:
            j += 1
        n = j - i
        while n > 0:
            k = min(9, n)
            out.append(str(k) + s[i])
            n -= k
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
