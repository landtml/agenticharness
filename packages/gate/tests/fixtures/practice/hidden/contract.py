from urh_gate import Contract, Example, FunctionSpec, Property
from urh_gate import gen as g
from urh_gate.contract import load_sibling

REF = load_sibling(__file__, "reference.py")

ARGS = g.tuples(g.lists(g.sampled_from(["a", "b", "c", "d", "", "A", "aa"]), 0, 30), g.integers(-2, 8))

CONTRACT = Contract(
    name="practice-dedupe",
    functions=[FunctionSpec("dedupe", ARGS, REF.dedupe, random_cases=300)],
    examples=[
        Example("dedupe", [["b", "a", "b", "c"], 2], ["b", "a"]),
        Example("dedupe", [[], 0], []),
        Example("dedupe", [["a"], -1], raises=True),
    ],
    properties=[
        Property(
            "distinct",
            g.tuples(g.lists(g.sampled_from("abcde"), 0, 20), g.integers(0, 6)),
            lambda x: [("dedupe", list(x))],
            lambda x, o: o[0].kind == "value" and len(set(o[0].value)) == len(o[0].value) or "duplicates",
        ),
    ],
)
