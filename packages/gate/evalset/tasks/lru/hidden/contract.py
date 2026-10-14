from urh_gate import Contract, Example, FunctionSpec, Property
from urh_gate import gen as g
from urh_gate.contract import load_sibling

REF = load_sibling(__file__, "reference.py")
reference = REF.lru_evictions


def _draw(rng, size):
    r = rng.random()
    cap = rng.choice([0, -1]) if r < 0.05 else rng.choice([1, 1, 2, 2, 3, 4, 5, rng.randint(1, 12)])
    keys = rng.choice(
        [
            ["a", "b", "c"],
            ["a", "b", "c", "d", "e"],
            ["", "a", "A", " "],
            [str(i) for i in range(20)],
            ["x", "xx", "xxx", "1", "01"],
        ]
    )
    n = rng.randint(0, min(60, 2 + size))
    acc = [rng.choice(keys) for _ in range(n)]
    if acc and rng.random() < 0.3:
        i = rng.randrange(len(acc))
        acc[i:i] = [acc[i]] * rng.randint(1, 3)  # immediate repeats
    return [cap, acc]


EDGES = [
    [1, []],
    [1, ["a"]],
    [1, ["a", "a"]],
    [1, ["a", "b"]],
    [1, ["a", "b", "a"]],
    [2, ["a", "b", "a", "c", "b", "d"]],
    [2, ["a", "b", "c"]],
    [2, ["a", "b", "a", "c"]],
    [3, ["a", "b", "c", "a", "d", "b", "e"]],
    [0, ["a"]],
    [-1, []],
    [0, []],
    [2, ["", "", "a", "b"]],
    [2, ["a", "b", "b", "a", "c"]],
    [3, ["a", "b", "c", "d", "a", "b", "c", "d"]],
    [1, ["", "a", ""]],
    [5, ["a", "b"]],
    [2, ["a", "a", "a", "b", "c", "a"]],
]


def _shrink(args):
    cap, acc = args
    out = [[cap, acc[:i] + acc[i + 1 :]] for i in range(len(acc))]
    if cap > 1:
        out.append([cap - 1, acc])
    return out


def _count(x, o):
    cap, acc = x
    if o[0].kind != "value":
        return cap < 1 or "unexpected error"
    ev = o[0].value
    distinct = len(set(acc))
    # Every eviction makes room for a miss; the cache ends with min(cap, #distinct) keys.
    if len(ev) < max(0, distinct - cap):
        return "too few evictions"
    return all(e in acc for e in ev) or "evicted a key never accessed"


CONTRACT = Contract(
    name="lru",
    functions=[
        FunctionSpec(
            "lru_evictions", g.custom(_draw, edges=lambda: EDGES, shrink=_shrink), reference, random_cases=500
        )
    ],
    examples=[
        Example("lru_evictions", [2, ["a", "b", "a", "c", "b", "d"]], ["b", "a", "c"]),
        Example("lru_evictions", [1, []], []),
        Example("lru_evictions", [0, ["a"]], raises=True),
    ],
    properties=[
        Property(
            "eviction-count",
            g.custom(
                lambda rng, size: [
                    rng.randint(1, 4),
                    [rng.choice("abcdef") for _ in range(rng.randint(0, 30))],
                ]
            ),
            lambda x: [("lru_evictions", list(x))],
            _count,
        ),
    ],
)
