from urh_gate import Contract, Example, FunctionSpec, Property
from urh_gate import gen as g
from urh_gate.contract import load_sibling

REF = load_sibling(__file__, "reference.py")
NUM = REF.NUM
PRE_ID = REF.PRE_ID
BUILD_ID = REF.BUILD_ID
SEMVER = REF.SEMVER
_parse = REF._parse
_cmp_ids = REF._cmp_ids
reference = REF.compare_versions


IDS = [
    "alpha",
    "beta",
    "rc",
    "0",
    "1",
    "2",
    "11",
    "9",
    "10",
    "a",
    "A",
    "Z",
    "z",
    "-",
    "x-y",
    "1a",
    "a1",
    "00a",
    "0a",
    "-1",
    "1-",
]


def _version(rng, size):
    nums = [
        rng.choice([0, 0, 1, 1, 2, 9, 10, 11, rng.randint(0, 100), rng.randint(0, 10**12)]) for _ in range(3)
    ]
    v = "%d.%d.%d" % tuple(nums)
    if rng.random() < 0.6:
        v += "-" + ".".join(rng.choice(IDS) for _ in range(rng.randint(1, 4)))
    if rng.random() < 0.3:
        v += "+" + ".".join(
            rng.choice(IDS + ["001", "build", "sha.5114f85"]) for _ in range(rng.randint(1, 3))
        )
    return v


BAD = [
    "",
    "1",
    "1.0",
    "1.0.0.0",
    "01.0.0",
    "1.01.0",
    "1.0.01",
    "v1.0.0",
    " 1.0.0",
    "1.0.0 ",
    "1.0.0-",
    "1.0.0+",
    "1.0.0-01",
    "1.0.0-a..b",
    "1.0.0-a.",
    "1.0.0-.a",
    "1.0.0+a..b",
    "1.0.0-a_b",
    "1.0.0+a_b",
    "1.0.0-é",
    "1.0.0-١",
    "١.0.0",
    "-1.0.0",
    "1.-1.0",
    "1.0.0-a+",
    "1.0.0++a",
    "1..0",
    "a.b.c",
    "1.0.0-a b",
    "1.0.0\n",
    "1.0.0-00",
    "1.0.0-0.01",
    "1.0.0-²",
]


def _mutate(rng, v):
    if rng.random() < 0.5:
        return rng.choice(BAD)
    i = rng.randint(0, len(v))
    return v[:i] + rng.choice(["0", ".", "-", "+", "_", " ", "v", ""]) + v[i + 1 :]


def _draw(rng, size):
    a = _version(rng, size)
    r = rng.random()
    if r < 0.25:
        b = a  # equal
        if rng.random() < 0.5 and "+" not in a:
            b = a + "+" + rng.choice(["x", "001", "b.2"])
    elif r < 0.5:
        # share the core, differ in prerelease
        core = a.split("-")[0].split("+")[0]
        b = core + (
            "" if rng.random() < 0.2 else "-" + ".".join(rng.choice(IDS) for _ in range(rng.randint(1, 4)))
        )
    else:
        b = _version(rng, size)
    if rng.random() < 0.12:
        a = _mutate(rng, a)
    if rng.random() < 0.12:
        b = _mutate(rng, b)
    return [a, b] if rng.random() < 0.5 else [b, a]


ORDER = [
    "1.0.0-alpha",
    "1.0.0-alpha.1",
    "1.0.0-alpha.beta",
    "1.0.0-beta",
    "1.0.0-beta.2",
    "1.0.0-beta.11",
    "1.0.0-rc.1",
    "1.0.0",
]
EDGES = (
    [[a, b] for a, b in zip(ORDER, ORDER[1:], strict=False)]
    + [[b, a] for a, b in zip(ORDER, ORDER[1:], strict=False)]
    + [
        ["2.0.0", "10.0.0"],
        ["1.10.0", "1.9.0"],
        ["1.0.10", "1.0.9"],
        ["1.0.0+a", "1.0.0+b"],
        ["1.0.0", "1.0.0"],
        ["1.0.0-1", "1.0.0-a"],
        ["1.0.0-a", "1.0.0-1"],
        ["1.0.0-2", "1.0.0-10"],
        ["1.0.0-a.b", "1.0.0-a"],
        ["1.0.0-A", "1.0.0-a"],
        ["1.0.0-a-b", "1.0.0-a"],
        ["1.0.0-0", "1.0.0-00a"],
        ["1.0.0-1a", "1.0.0-2"],
        ["1.0.0-rc.1+build", "1.0.0-rc.1"],
        ["1.0.0+001", "1.0.0"],
        ["0.0.0", "0.0.0-0"],
        ["99999999999999999999.0.0", "100000000000000000000.0.0"],
        ["1.0.0-x.7.z.92", "1.0.0-x.7.z.93"],
    ]
    + [[b, "1.0.0"] for b in BAD]
    + [["1.0.0", b] for b in BAD[:12]]
)


def _shrink(args):
    a, b = args
    out = []
    for i in range(len(a)):
        out.append([a[:i] + a[i + 1 :], b])
    for i in range(len(b)):
        out.append([a, b[:i] + b[i + 1 :]])
    return out


def _antisym(x, o):
    if o[0].kind == "error" or o[1].kind == "error":
        return (o[0].kind == o[1].kind) or "validity depends on argument order"
    return (o[0].value == -o[1].value) or "compare(a,b) != -compare(b,a)"


CONTRACT = Contract(
    name="semver",
    functions=[
        FunctionSpec(
            "compare_versions",
            g.custom(_draw, edges=lambda: EDGES, shrink=_shrink),
            reference,
            random_cases=800,
        )
    ],
    examples=[
        Example("compare_versions", ["2.0.0", "10.0.0"], -1),
        Example("compare_versions", ["1.0.0-alpha", "1.0.0-alpha.1"], -1),
        Example("compare_versions", ["1.0.0-beta.11", "1.0.0-beta.2"], 1),
        Example("compare_versions", ["1.0.0+a", "1.0.0+b"], 0),
        Example("compare_versions", ["1.0.0-rc.1", "1.0.0"], -1),
        Example("compare_versions", ["01.0.0", "1.0.0"], raises=True),
    ],
    properties=[
        Property(
            "antisymmetric",
            g.custom(_draw),
            lambda x: [("compare_versions", [x[0], x[1]]), ("compare_versions", [x[1], x[0]])],
            _antisym,
        ),
    ],
)
