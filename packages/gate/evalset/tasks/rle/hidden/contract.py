from urh_gate import Contract, Example, FunctionSpec, Property, Ref
from urh_gate import gen as g
from urh_gate.contract import load_sibling

REF = load_sibling(__file__, "reference.py")
rle_encode = REF.rle_encode
rle_decode = REF.rle_decode


ALPHA = ["ab", "a", "ab1", "0123456789", "a 1\n", "aA", "xyz9", "é١²"]


def _plain(rng, size):
    alpha = rng.choice(ALPHA)
    out = ""
    for _ in range(rng.randint(0, min(10, 1 + size // 8))):
        out += rng.choice(alpha) * rng.choice([1, 1, 2, 3, 8, 9, 10, 11, 17, 18, 19, 27, rng.randint(1, 40)])
    return out


def _enc_input(rng, size):
    r = rng.random()
    if r < 0.5:
        s = rle_encode(_plain(rng, size))
        if rng.random() < 0.3:
            # non-canonical but well formed: split runs, adjacent same chars
            s = "".join("1" + ch for ch in rle_decode(s)[:20]) if s else s
        return [s]
    s = rle_encode(_plain(rng, size))
    k = rng.randint(0, 4)
    if k == 0:
        s = s + rng.choice("1a0")
    elif k == 1 and s:
        s = s[:-1]
    elif k == 2:
        s = "0a" + s
    elif k == 3 and len(s) >= 2:
        i = rng.randrange(0, len(s), 2)
        s = s[:i] + rng.choice("a0١² -") + s[i + 1 :]
    else:
        s = rng.choice(["0a", "a", "1", "a1", "10a", "²a", "١a", " 1a", "1a2", "-1a", "+1a"])
    return [s]


ENC_EDGES = [
    [s]
    for s in [
        "",
        "a",
        "aa",
        "a" * 9,
        "a" * 10,
        "a" * 18,
        "a" * 19,
        "a" * 27,
        "112",
        "1",
        "11",
        "111111111111",
        "ab",
        "aab",
        "abb",
        "a1a",
        " ",
        "\n\n",
        "0",
        "00",
        "9" * 10,
        "aaaaaaaaaaaab",
    ]
]
DEC_EDGES = [
    [s]
    for s in [
        "",
        "1a",
        "9a",
        "1a1a",
        "21",
        "2112",
        "9a3a1b",
        "0a",
        "a",
        "1",
        "1a2",
        "a1",
        "10a",
        "11",
        "99",
        "91",
        "1 ",
        "1\n",
        "²a",
        "١a",
        "1a0b",
        "9a9a9a",
        "aa",
        "1a1",
    ]
]


def _sh(args):
    s = args[0]
    return [[s[:i] + s[i + 1 :]] for i in range(len(s))] + [[s[:i] + s[i + 2 :]] for i in range(0, len(s), 2)]


CONTRACT = Contract(
    name="rle",
    functions=[
        FunctionSpec(
            "rle_encode",
            g.custom(lambda rng, size: [_plain(rng, size)], edges=lambda: ENC_EDGES, shrink=_sh),
            rle_encode,
            random_cases=400,
        ),
        FunctionSpec(
            "rle_decode",
            g.custom(_enc_input, edges=lambda: DEC_EDGES, shrink=_sh),
            rle_decode,
            random_cases=500,
        ),
    ],
    examples=[
        Example("rle_encode", ["aaaaaaaaaaaab"], "9a3a1b"),
        Example("rle_encode", ["112"], "2112"),
        Example("rle_encode", [""], ""),
        Example("rle_decode", ["1a1a"], "aa"),
        Example("rle_decode", ["0a"], raises=True),
        Example("rle_decode", ["1a1"], raises=True),
    ],
    properties=[
        Property(
            "round-trip",
            g.custom(lambda rng, size: _plain(rng, size)),
            lambda s: [("rle_encode", [s]), ("rle_decode", [Ref(0)])],
            lambda s, o: (o[1].kind == "value" and o[1].value == s) or "decode(encode(s)) != s",
        ),
    ],
)
