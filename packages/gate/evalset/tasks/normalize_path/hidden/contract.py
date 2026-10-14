from urh_gate import Contract, Example, FunctionSpec, Property, Ref
from urh_gate import gen as g
from urh_gate.contract import load_sibling

REF = load_sibling(__file__, "reference.py")
reference = REF.normalize_path


PARTS = ["a", "b", "c", "..", "..", ".", ".", "", "...", ".hidden", "a.b", "..a", "a..", " ", "x y", "ü"]


def _path(rng, size):
    n = rng.randint(0, min(12, 1 + size // 6))
    lead = rng.choice(["", "", "/", "//", "///", "./", "../"])
    trail = rng.choice(["", "", "/", "//", "/.", "/.."])
    return lead + "/".join(rng.choice(PARTS) for _ in range(n)) + trail


EDGES = [
    [e]
    for e in [
        "",
        "/",
        "//",
        "///",
        ".",
        "./",
        "..",
        "../",
        "/..",
        "/../..",
        "a",
        "a/",
        "a/..",
        "a/../..",
        "../a",
        "../../a",
        "a/b/../../..",
        "/a//b/./c/..",
        "./a/./b/",
        "...",
        ".../..",
        ".hidden",
        "/a/b/c/../../../..",
        "a//b",
        "//a",
        "a/./",
        "././.",
        "../..",
        "a/../../b/..",
        "/./",
        "/a/..",
        "..a/..",
        "a../b",
    ]
]


def _shrink(args):
    p = args[0]
    parts = p.split("/")
    out = [["/".join(parts[:i] + parts[i + 1 :])] for i in range(len(parts))]
    out += [[p[:i] + p[i + 1 :]] for i in range(len(p))]
    return out


def _canonical(x, o):
    r = o[0]
    if r.kind != "value" or type(r.value) is not str:
        return "no string result"
    v = r.value
    if v != "/" and v.endswith("/"):
        return "trailing slash"
    if "//" in v or "/./" in v or v.startswith("./") or v.endswith("/."):
        return "not normalized"
    return (o[1].kind == "value" and o[1].value == v) or "not idempotent"


CONTRACT = Contract(
    name="normalize_path",
    functions=[
        FunctionSpec(
            "normalize_path",
            g.custom(lambda rng, size: [_path(rng, size)], edges=lambda: EDGES, shrink=_shrink),
            reference,
            random_cases=600,
        )
    ],
    examples=[
        Example("normalize_path", ["/a//b/./c/.."], "/a/b"),
        Example("normalize_path", ["a/b/../../.."], ".."),
        Example("normalize_path", ["///"], "/"),
        Example("normalize_path", [""], "."),
        Example("normalize_path", ["./"], "."),
    ],
    properties=[
        Property(
            "canonical-idempotent",
            g.custom(lambda rng, size: _path(rng, size)),
            lambda p: [("normalize_path", [p]), ("normalize_path", [Ref(0)])],
            _canonical,
        ),
    ],
)
