import string

from urh_gate import Contract, Example, FunctionSpec, Property
from urh_gate import gen as g
from urh_gate.contract import load_sibling

REF = load_sibling(__file__, "reference.py")
reference = REF.wrap


WS = [" ", " ", " ", "  ", "\n", "\t", "\r\n", " \n ", " ", " ", "\x0b", "\x0c"]


def _text(rng, size):
    words = []
    for _ in range(rng.randint(0, min(25, 2 + size // 4))):
        n = rng.choice([1, 1, 2, 3, 4, 5, 6, 8, 12, rng.randint(1, 30)])
        alpha = rng.choice([string.ascii_lowercase, string.ascii_letters + string.digits + ".,!-'", "äöüß€"])
        words.append("".join(rng.choice(alpha) for _ in range(n)))
    out = rng.choice(["", "", " ", "\n"])
    for i, w in enumerate(words):
        out += w + (rng.choice(WS) if i < len(words) - 1 else rng.choice(["", "", " ", "\n"]))
    return out


def _draw(rng, size):
    text = _text(rng, size)
    r = rng.random()
    if r < 0.05:
        width = rng.choice([0, -1, -10])
    elif r < 0.35:
        width = rng.randint(1, 4)
    else:
        width = rng.randint(1, 40)
    return [text, width]


EDGES = [
    ["", 5],
    ["   \n\t ", 5],
    ["a", 1],
    ["ab", 1],
    ["the quick brown fox", 10],
    ["abcdefgh ij", 3],
    ["abcdef x", 3],
    ["ab cdefg", 4],
    ["abc", 3],
    ["abc def", 7],
    ["abc def", 6],
    ["abc  def", 7],
    ["a b c d", 1],
    ["abcd", 2],
    ["abcdef", 3],
    ["x abcdef", 3],
    ["ab abcdef cd", 3],
    ["a\nb", 3],
    ["a\n\nb", 10],
    [" lead", 4],
    ["trail ", 5],
    ["one", 0],
    ["one", -5],
    ["aaaa bb", 4],
    ["aaaaa b", 4],
    ["aa bb", 5],
    ["aaa bbb ccc", 7],
    ["aaa bbb ccc", 8],
    ["abcdefgh", 4],
    ["abcdefgh i", 4],
    ["a" * 9 + " b", 4],
]


def _shrink(args):
    text, width = args
    out = []
    words = text.split()
    for i in range(len(words)):
        out.append([" ".join(words[:i] + words[i + 1 :]), width])
    for i in range(min(len(text), 30)):
        out.append([text[:i] + text[i + 1 :], width])
    if width > 1:
        out.append([text, width - 1])
    return out


def _invariants(x, o):
    text, width = x
    if o[0].kind == "error":
        return width < 1 or "raised on valid width"
    lines = o[0].value
    if type(lines) is not list or any(type(l) is not str for l in lines):
        return "not a list of str"
    for l in lines:
        if not l or len(l) > width or l != l.strip() or "  " in l:
            return f"bad line {l[:30]!r}"
    if "".join("".join(l.split()) for l in lines) != "".join(text.split()):
        return "characters lost or added"
    return True


CONTRACT = Contract(
    name="wrap",
    functions=[
        FunctionSpec(
            "wrap", g.custom(_draw, edges=lambda: EDGES, shrink=_shrink), reference, random_cases=600
        )
    ],
    examples=[
        Example("wrap", ["the quick brown fox", 10], ["the quick", "brown fox"]),
        Example("wrap", ["abcdefgh ij", 3], ["abc", "def", "gh", "ij"]),
        Example("wrap", ["abcdef x", 3], ["abc", "def", "x"]),
        Example("wrap", ["ab cdefg", 4], ["ab", "cdef", "g"]),
        Example("wrap", ["", 4], []),
        Example("wrap", ["a", 0], raises=True),
    ],
    properties=[
        Property(
            "line-invariants",
            g.custom(lambda rng, size: [_text(rng, size), rng.randint(1, 20)]),
            lambda x: [("wrap", list(x))],
            _invariants,
            cases=300,
        ),
    ],
)
