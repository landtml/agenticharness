def _runs(s):
    prev = None
    count = 0
    for ch in s:
        if ch == prev:
            count += 1
        else:
            if prev is not None:
                yield prev, count
            prev = ch
            count = 1
    if prev is not None:
        yield prev, count


def _chunks(ch, n):
    while n > 9:
        yield "9" + ch
        n -= 9
    yield str(n) + ch


def rle_encode(s: str) -> str:
    return "".join(part for ch, n in _runs(s) for part in _chunks(ch, n))


def rle_decode(s: str) -> str:
    if len(s) % 2:
        raise ValueError("odd length")
    pieces = []
    it = iter(s)
    for digit, ch in zip(it, it):
        if digit not in "123456789":
            raise ValueError("invalid count")
        pieces.append(ch * int(digit))
    return "".join(pieces)
