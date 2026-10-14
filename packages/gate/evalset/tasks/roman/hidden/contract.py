from urh_gate import Contract, Example, FunctionSpec, Property, Ref
from urh_gate import gen as g
from urh_gate.contract import load_sibling

REF = load_sibling(__file__, "reference.py")
TABLE = REF.TABLE
int_to_roman = REF.int_to_roman
CANON = REF.CANON
roman_to_int = REF.roman_to_int


def _draw_int(rng, size):
    r = rng.random()
    if r < 0.75:
        return [rng.randint(1, 3999)]
    if r < 0.85:
        return [rng.choice([0, -1, 4000, 4001, 10000, -3999, 5000])]
    return [rng.choice([True, False, 1.0, 4.0, "4", None, [4]])]


def _draw_str(rng, size):
    r = rng.random()
    s = int_to_roman(rng.randint(1, 3999))
    if r < 0.5:
        return [s]
    k = rng.randint(0, 6)
    if k == 0 and s:
        i = rng.randrange(len(s))
        s = s[:i] + s[i + 1 :]
    elif k == 1:
        i = rng.randint(0, len(s))
        s = s[:i] + rng.choice("IVXLCDM") + s[i:]
    elif k == 2 and len(s) > 1:
        i = rng.randrange(len(s) - 1)
        s = s[:i] + s[i + 1] + s[i] + s[i + 2 :]
    elif k == 3:
        s = s.lower() if rng.random() < 0.5 else s[0].lower() + s[1:]
    elif k == 4:
        s = rng.choice(
            [
                "",
                " ",
                "IIII",
                "VV",
                "IC",
                "IL",
                "XM",
                "VX",
                "MMMM",
                "IIV",
                "XXL",
                "LL",
                "DD",
                "CCCC",
                "XXXX",
                "IXI",
                "IVI",
                "XCX",
                "CMC",
                "IIX",
                "VIV",
                "LXL",
                "DCD",
                "MCMM",
                "XIX",
                "MMMCMXCIXI",
                "I ",
                " I",
                "IΙ",
                "Ⅳ",
                "0",
                "N",
            ]
        )
    elif k == 5:
        s = s + rng.choice(["I", "V", "X", "M"])
    else:
        s = rng.choice("IVXLCDM") + s
    return [s]


INT_EDGES = [
    [1],
    [2],
    [3],
    [4],
    [5],
    [9],
    [10],
    [14],
    [40],
    [49],
    [90],
    [99],
    [400],
    [444],
    [900],
    [999],
    [1994],
    [3888],
    [3999],
    [0],
    [4000],
    [-1],
    [True],
    [1.0],
    ["1"],
    [None],
]
STR_EDGES = [
    [s]
    for s in [
        "I",
        "IV",
        "IX",
        "XL",
        "XC",
        "CD",
        "CM",
        "MMMCMXCIX",
        "MCMXCIV",
        "XLII",
        "",
        "IIII",
        "VV",
        "IC",
        "IL",
        "XM",
        "VX",
        "MMMM",
        "iv",
        "IIV",
        "IXX",
        "XCX",
        "CMM",
        "DM",
        "LC",
        "VL",
        "IVI",
        "XIIII",
        "LXL",
        "MMMCMXCIXX",
        "CCCC",
        "XXXX",
        "DD",
        "LL",
        "MMMDCCCLXXXVIII",
        "IIX",
        "XIX",
        "XXC",
    ]
]


def _shrink_int(args):
    n = args[0]
    if type(n) is not int:
        return []
    return [[v] for v in (1, n // 2, n - 1) if 1 <= v < n] if n >= 1 else [[0]]


def _shrink_str(args):
    s = args[0]
    return [[s[:i] + s[i + 1 :]] for i in range(len(s))]


CONTRACT = Contract(
    name="roman",
    functions=[
        FunctionSpec(
            "int_to_roman",
            g.custom(_draw_int, edges=lambda: INT_EDGES, shrink=_shrink_int),
            int_to_roman,
            random_cases=400,
            exhaustive=lambda: [[n] for n in range(1, 4000)],
        ),
        FunctionSpec(
            "roman_to_int",
            g.custom(_draw_str, edges=lambda: STR_EDGES, shrink=_shrink_str),
            roman_to_int,
            random_cases=600,
            exhaustive=lambda: [[int_to_roman(n)] for n in range(1, 4000)],
        ),
    ],
    examples=[
        Example("int_to_roman", [4], "IV"),
        Example("int_to_roman", [1994], "MCMXCIV"),
        Example("int_to_roman", [3999], "MMMCMXCIX"),
        Example("roman_to_int", ["MCMXCIV"], 1994),
        Example("roman_to_int", ["XLII"], 42),
        Example("roman_to_int", ["IIII"], raises=True),
    ],
    properties=[
        Property(
            "round-trip",
            g.integers(1, 3999).map(lambda n: n),
            lambda n: [("int_to_roman", [n]), ("roman_to_int", [Ref(0)])],
            lambda n, o: (o[1].kind == "value" and o[1].value == n) or "roman_to_int(int_to_roman(n)) != n",
            cases=300,
        ),
    ],
)
