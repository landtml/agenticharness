from urh_gate import Contract, Example, FunctionSpec, Property, Ref
from urh_gate import gen as g
from urh_gate.contract import load_sibling

REF = load_sibling(__file__, "reference.py")
reference = REF.merge_intervals


def _interval(rng, size):
    span = rng.choice([3, 10, 50, 1000])
    a = rng.randint(-span, span)
    b = a + rng.choice([0, 0, 1, 1, 2, rng.randint(0, span)])
    return [a, b]


def _draw(rng, size):
    n = rng.randint(0, min(12, 1 + size // 6))
    ivs = [_interval(rng, size) for _ in range(n)]
    if ivs and rng.random() < 0.3:
        ivs.append(list(rng.choice(ivs)))  # duplicate
    if ivs and rng.random() < 0.2:
        a, b = rng.choice(ivs)
        ivs.append([b, b + rng.randint(0, 3)])  # touching
    if ivs and rng.random() < 0.15:
        a, b = rng.choice(ivs)
        ivs.append([b + 1, b + 1 + rng.randint(0, 3)])  # adjacent but not touching
    if rng.random() < 0.1:
        ivs.insert(rng.randint(0, len(ivs)), [5, rng.randint(0, 4)])  # invalid
    rng.shuffle(ivs)
    return [ivs]


EDGES = (
    [[]],
    [[[1, 1]]],
    [[[1, 3], [3, 5]]],
    [[[1, 2], [3, 4]]],
    [[[3, 4], [1, 2]]],
    [[[1, 10], [2, 3]]],
    [[[2, 3], [1, 10]]],
    [[[1, 2], [1, 2]]],
    [[[-5, -1], [-1, 0]]],
    [[[2, 1]]],
    [[[1, 2], [4, 3]]],
    [[[5, 5], [1, 2]]],
    [[[1, 3], [2, 6], [8, 10]]],
    [[[0, 0], [0, 0], [0, 0]]],
    [[[1, 5], [2, 3], [4, 8], [10, 12], [9, 9]]],
    [[[1, 4], [0, 0]]],
    [[[1, 4], [0, 1]]],
    [[[1, 4], [5, 6]]],
    [[[1, 2], [2, 2], [2, 3]]],
    [[[-3, -2], [-1, 1]]],
    [[[10, 20], [0, 5], [5, 10]]],
    [[[1, 3], [0, 2], [5, 6], [4, 4]]],
)


def _shrink(args):
    ivs = args[0]
    out = [[ivs[:i] + ivs[i + 1 :]] for i in range(len(ivs))]
    for i, (a, b) in enumerate(ivs):
        for na, nb in ((a // 2, b // 2), (a, a), (a - 1 if a > 0 else a + 1, b)):
            if [na, nb] != [a, b]:
                out.append([ivs[:i] + [[na, nb]] + ivs[i + 1 :]])
    return out


ARGS = g.custom(_draw, edges=lambda: [list(e) for e in EDGES], shrink=_shrink)


def _same_points(x, o):
    if o[0].kind != "value":
        return o[0].kind == "error" and any(a > b for a, b in x) or "unexpected outcome"
    pts = set()
    for a, b in x:
        pts.update(range(a, b + 1))
    got = set()
    for a, b in o[0].value:
        got.update(range(a, b + 1))
    if pts != got:
        return "covers different points"
    out = o[0].value
    for (_a1, b1), (a2, _b2) in zip(out, out[1:], strict=False):
        if not (b1 < a2):
            return "output intervals overlap, touch or are unsorted"
    return True


def _idempotent(x, o):
    if o[0].kind == "error":
        return True
    return (o[1].kind == "value" and o[1].value == o[0].value) or "merging the output again changed it"


SMALL = g.custom(lambda rng, size: [_interval(rng, 0) for _ in range(rng.randint(0, 8))])

CONTRACT = Contract(
    name="merge_intervals",
    functions=[FunctionSpec("merge_intervals", ARGS, reference, random_cases=500)],
    examples=[
        Example("merge_intervals", [[[1, 3], [2, 6], [8, 10]]], [[1, 6], [8, 10]]),
        Example("merge_intervals", [[[5, 5], [1, 2]]], [[1, 2], [5, 5]]),
        Example("merge_intervals", [[]], []),
        Example("merge_intervals", [[[3, 2]]], raises=True),
    ],
    properties=[
        Property(
            "covers-same-points",
            SMALL.filter(lambda x: all(b - a < 200 for a, b in x)),
            lambda x: [("merge_intervals", [x])],
            _same_points,
        ),
        Property(
            "idempotent",
            SMALL,
            lambda x: [("merge_intervals", [x])] + [("merge_intervals", [Ref(0)])],
            _idempotent,
        ),
    ],
)
