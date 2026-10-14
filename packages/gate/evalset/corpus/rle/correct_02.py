def rle_encode(s: str) -> str:
    out = []
    i = 0
    n = len(s)
    while i < n:
        ch = s[i]
        j = i
        while j < n and s[j] == ch:
            j += 1
        remaining = j - i
        while remaining > 9:
            out.append("9" + ch)
            remaining -= 9
        out.append(str(remaining) + ch)
        i = j
    return "".join(out)


def rle_decode(s: str) -> str:
    if len(s) % 2:
        raise ValueError("odd length")
    out = []
    i = 0
    while i < len(s):
        digit = s[i]
        if not ("1" <= digit <= "9"):
            raise ValueError("bad count")
        out.append(s[i + 1] * (ord(digit) - ord("0")))
        i += 2
    return "".join(out)
