"""Contract for the slug example of the harness scaffold (step 2: unicode folding).

Written from the step instructions alone, as a cross-check: the scaffold's
own hidden tests and mutant corpora were not used to tune it.
"""

from urh_gate import Contract, Example, FunctionSpec, Property, Ref
from urh_gate import gen as g
from urh_gate.contract import load_sibling

REF = load_sibling(__file__, "reference.py")

POOLS = [
    "abcXYZ019",
    " _-.,!?/\\'\"\t\n@#$%^&*()[]{}~`+=|<>",
    "éèêëàâäçñøåßÆœÉÜÖĳǅ",
    "’–—…ﬁ①²½́ 　中文١ＡÅ",
]


def _text(rng, size):
    pool = "".join(p for p in POOLS if rng.random() < 0.7) or POOLS[0]
    return ["".join(rng.choice(pool) for _ in range(rng.randint(0, 4 + size)))]


EDGES = [
    [s]
    for s in [
        "",
        "-",
        "--",
        "a",
        "_",
        "a_b",
        "A-B",
        "a--b",
        "-a-",
        " a ",
        "x" * 120,
        "a b " * 30,
        "Hello, World!",
        "  --A  b--  ",
        "Crème Brûlée",
        "Ærø",
        "ß",
        "ﬁ",
        "①",
        "½",
        "é",
        " a ",
        "a\tb\nc",
        "中文",
        "１２３",
        "Å",
        "ǅ",
        "0",
        "00-11",
        "a.b",
        "a/b",
        "a'b",
        "UPPER",
        "MiXeD 123",
    ]
]


def _shrink(args):
    s = args[0]
    return [[s[:i] + s[i + 1 :]] for i in range(len(s))]


CONTRACT = Contract(
    name="slug",
    functions=[
        FunctionSpec(
            "slugify", g.custom(_text, edges=lambda: EDGES, shrink=_shrink), REF.slugify, random_cases=400
        ),
    ],
    target="slug.py",
    examples=[
        Example("slugify", ["Hello, World!"], "hello-world"),
        Example("slugify", ["  --A  b--  "], "a-b"),
        Example("slugify", [""], ""),
        Example("slugify", ["Crème Brûlée"], "creme-brulee"),
        Example("slugify", ["Ærø"], "r"),
    ],
    properties=[
        Property(
            "idempotent",
            g.custom(lambda rng, size: _text(rng, size)[0]),
            lambda s: [("slugify", [s]), ("slugify", [Ref(0)])],
            lambda s, o: o[0].kind == o[1].kind == "value" and o[0].value == o[1].value or "not idempotent",
        ),
    ],
)
