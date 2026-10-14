from urh_gate import Contract, Example, FunctionSpec, Property
from urh_gate import gen as g
from urh_gate.contract import load_sibling

REF = load_sibling(__file__, "reference.py")
UNITS = REF.UNITS
reference = REF.parse_duration


def _valid(rng, size):
    parts = []
    for u, _ in UNITS:
        if rng.random() < 0.5:
            n = rng.choice([0, 1, 9, 10, 59, 60, 99, 100, 3600, rng.randint(0, 10 ** rng.randint(1, 6))])
            digits = str(n)
            if rng.random() < 0.15:
                digits = "0" * rng.randint(1, 3) + digits
            parts.append(digits + u)
    if not parts:
        parts.append(str(rng.randint(0, 500)) + rng.choice("dhms"))
    return "".join(parts)


def _mutate(rng, s):
    ops = rng.randint(1, 2)
    alphabet = "0123456789dhmsDHMS -+.xw١²"
    for _ in range(ops):
        k = rng.randint(0, 5)
        if k == 0 and s:
            i = rng.randrange(len(s))
            s = s[:i] + s[i + 1 :]
        elif k == 1:
            i = rng.randint(0, len(s))
            s = s[:i] + rng.choice(alphabet) + s[i:]
        elif k == 2 and len(s) > 1:
            a = rng.randrange(len(s))
            b = rng.randrange(len(s))
            l = list(s)
            l[a], l[b] = l[b], l[a]
            s = "".join(l)
        elif k == 3:
            s = s + s[-2:] if len(s) >= 2 else s + "1s"
        elif k == 4:
            s = s.upper()
        else:
            s = rng.choice(
                [
                    "",
                    " ",
                    "h",
                    "10",
                    "1h1h",
                    "1m1h",
                    "1s1m",
                    "+1s",
                    "-1s",
                    "1.5h",
                    " 1s",
                    "1s ",
                    "1h 1m",
                    "1H",
                    "١s",
                    "²s",
                    "1hm",
                    "1d1d",
                ]
            )
    return s


def _draw(rng, size):
    s = _valid(rng, size)
    return [s if rng.random() < 0.55 else _mutate(rng, s)]


EDGES = [
    "",
    "0s",
    "1s",
    "1m",
    "1h",
    "1d",
    "007s",
    "90m",
    "1d1h1m1s",
    "1d5s",
    "h",
    "10",
    "1h1h",
    "1m1h",
    "1H",
    " 1s",
    "1s ",
    "-1s",
    "+1s",
    "1.5h",
    "1h 30m",
    "١s",
    "²s",
    "1s1s",
    "0d0h0m0s",
    "1hm",
    "s1",
    "1x",
    "99999999999999999999s",
    "1d1h1h",
    "1\n",
    "1s\n",
]


def _shrink(args):
    s = args[0]
    out = [[s[:i] + s[i + 1 :]] for i in range(len(s))]
    out += [[s[:i] + "1" + s[i + 1 :]] for i, ch in enumerate(s) if ch.isdigit() and ch != "1"]
    return out


ARGS = g.custom(_draw, edges=lambda: [[e] for e in EDGES], shrink=_shrink)

CONTRACT = Contract(
    name="parse_duration",
    functions=[FunctionSpec("parse_duration", ARGS, reference, random_cases=500)],
    examples=[
        Example("parse_duration", ["1h30m"], 5400),
        Example("parse_duration", ["0s"], 0),
        Example("parse_duration", ["2d"], 172800),
        Example("parse_duration", ["1d1h1m1s"], 90061),
        Example("parse_duration", [""], raises=True),
        Example("parse_duration", ["1m1h"], raises=True),
    ],
    properties=[
        Property(
            "additive",
            g.custom(lambda rng, size: [rng.randint(0, 999) for _ in range(4)]),
            lambda x: (
                [("parse_duration", ["%dd%dh%dm%ds" % tuple(x)])]
                + [("parse_duration", ["%d%s" % (v, u)]) for v, (u, _) in zip(x, UNITS, strict=False)]
            ),
            lambda x, o: (
                o[0].kind == "value"
                and all(p.kind == "value" for p in o[1:])
                and o[0].value == sum(p.value for p in o[1:])
                or "sum of parts differs"
            ),
        ),
    ],
)
