"""Constant-guided inputs: aim tests at the thresholds the candidate itself names.

Random inputs rarely reach a branch like ``if len(items) > 4096`` or a magic
value like ``if s == "MMDCCCLXXXVIII"``. The gate can read the candidate's
source, so it harvests the literals in it (ints, short strings, ``chr(n)``
characters) and transforms known-valid base inputs around them: integers set
to c-1, c, c+1, 2c, lists stretched to length c+1 with repeated or fresh
elements, strings padded, repeated or seeded with the literal. A fixed ladder
of common limits (powers of two, 10**9, 2**31, 2**53, ...) and a set of rare
characters are always added, so a threshold computed at run time is still
probed.

The base inputs are hidden examples, edge cases and a few random draws; every
transformed input is judged by the reference like any other, so an input the
spec calls invalid simply has to raise the spec's error.
"""

import ast
import random

LADDER_INTS = [
    2,
    3,
    7,
    8,
    9,
    10,
    12,
    15,
    16,
    17,
    20,
    25,
    30,
    31,
    32,
    33,
    40,
    50,
    63,
    64,
    65,
    99,
    100,
    127,
    128,
    200,
    255,
    256,
    500,
    512,
    1000,
    1024,
    4096,
    10**4,
    65536,
    10**6,
    10**9,
    2**31 - 1,
    2**31,
    2**32,
    2**53,
    2**53 + 1,
    2**63,
    2**64,
    10**18,
]
RARE_CHARS = [
    "\x00",
    "\\",
    " ",
    "\t",
    "\n",
    "\r",
    "_",
    "-",
    ".",
    "/",
    "'",
    '"',
    "%",
    "{",
    "é",
    "١",
    "²",
    " ",
    "\U0001f600",
    "﻿",
]
MAX_LEN = 5000  # longest list or string the phase builds
MAX_CONST = 10**20


def harvest(source):
    """Ints and short strings that appear as literals in the candidate."""
    ints, strs = set(), set()
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return [], []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant):
            v = node.value
            if type(v) is int and 2 <= abs(v) <= MAX_CONST:
                ints.add(v)
            elif type(v) is str and 0 < len(v) <= 40:
                strs.add(v)
        elif (
            isinstance(node, ast.UnaryOp)
            and isinstance(node.op, ast.USub)
            and isinstance(node.operand, ast.Constant)
            and type(node.operand.value) is int
        ):
            if 2 <= node.operand.value <= MAX_CONST:
                ints.add(-node.operand.value)
        elif (
            isinstance(node, ast.BinOp)
            and isinstance(node.op, ast.Pow)
            and isinstance(node.left, ast.Constant)
            and isinstance(node.right, ast.Constant)
        ):
            a, b = node.left.value, node.right.value
            if type(a) is int and type(b) is int and 0 < a <= 16 and 0 <= b <= 70:
                v = a**b
                ints.update(x for x in (v - 1, v, v + 1) if 2 <= x <= MAX_CONST)
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "chr"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and type(node.args[0].value) is int
        ):
            try:
                strs.add(chr(node.args[0].value))
            except (ValueError, OverflowError):
                pass
    return sorted(ints), sorted(strs, key=lambda s: (len(s), s))


def _leaves(value, path=()):
    """Yield (path, leaf) for ints, strs and lists inside a nested args structure."""
    t = type(value)
    if t is list:
        yield path, value
        for i, v in enumerate(value):
            yield from _leaves(v, path + (i,))
    elif t is int or t is str:
        yield path, value


def _replace(value, path, new):
    if not path:
        return new
    out = list(value)
    out[path[0]] = _replace(value[path[0]], path[1:], new)
    return out


def _fresh(elem, i, width=None):
    t = type(elem)
    if t is str:
        base = elem if width is None else (elem or "k").ljust(max(1, width - len(str(i))), (elem or "k")[-1:])
        return base + str(i)
    if t is int:
        return elem + 3 * i
    if t is list:
        return [_fresh(x, i, width) for x in elem]
    return elem


def _int_values(c):
    return [c - 1, c, c + 1, 2 * c, 3 * c, -c]


def _str_variants(s, c=None, lit=None):
    """Variants of one string leaf around a length constant ``c`` or a literal ``lit``."""
    out = []
    if lit is not None:
        out += [lit, lit + s, s + lit, s[: len(s) // 2] + lit + s[len(s) // 2 :]]
    if c is not None and 0 < c <= MAX_LEN:
        for n in (c - 1, c, c + 1):
            if n <= 0:
                continue
            if s:
                out.append((s * (n // len(s) + 1))[:n])  # repeat
                out.append(s + " " * max(0, n - len(s)))  # pad with spaces
                out.append(s[:1] * n + s[1:])  # stretch first char
                out.append(" ".join([s] * max(1, n // (len(s) + 1) + 1)))  # many words
            else:
                out.append("a" * n)
        out += _segment_variants(s, c)
    return out


SEPARATORS = ".", "/", ",", ";", " ", "-", ":"


def _segment_variants(s, c):
    """Grow the number of separator-delimited segments to about c."""
    out = []
    for sep in SEPARATORS:
        if sep in s and 0 < c <= 512:
            head, _, tail = s.rpartition(sep)
            tail = tail or "x"
            grown = s + (sep + tail) * max(0, c + 1 - s.count(sep))
            out += [grown, grown + sep + "2", grown + sep + "3"]
    return out


def _list_variants(lst, c):
    out = []
    if 0 < c < MAX_LEN and lst:
        for n in (c, c + 1, c + 2, 2 * c):
            if n > MAX_LEN:
                continue
            out.append([lst[i % len(lst)] for i in range(n)])  # cycle
            out.append([_fresh(lst[i % len(lst)], i) for i in range(n)])  # fresh, distinct
        if type(lst[0]) is str and c <= 64:
            out.append([_fresh(lst[0], i, width=c) for i in range(4)])  # long, shared prefix
    return out


def _near_duplicates(lst, lits):
    """Lists that hold an element next to a near copy of it: catches dedupe or
    lookup keys that normalise (strip, lower, prefix) when the spec says exact."""
    out = []
    strs = [x for x in lst if type(x) is str]
    if not strs:
        return out
    e = strs[0]
    copies = [
        e.upper(),
        e.lower(),
        e.capitalize(),
        " " + e,
        e + " ",
        "\t" + e,
        e + "\n",
        e * 2,
        e + "x",
        "x" + e,
        e[:-1] if len(e) > 1 else e + e,
    ]
    copies += [lit + e for lit in lits[:6]] + [e + lit for lit in lits[:6]]
    for c in copies:
        if c != e:
            out.append(lst + [c])
            out.append([c] + lst)
    return out


def _joint(args, c, mode):
    """Apply one constant to every leaf at once (thresholds that need two conditions)."""

    def walk(v, depth):
        t = type(v)
        if t is int:
            return c if mode == 0 else c + 1
        if t is str:
            if not v or c > MAX_LEN:
                return v
            if mode == 0:
                return " ".join([v] * max(1, (c + 1) // (len(v) + 1) + 1))
            return (v * ((c + 1) // len(v) + 1))[: c + 1]
        if t is list:
            items = [walk(x, depth + 1) for x in v]
            if depth == 0 and items and c < MAX_LEN:
                n = c + 1 if mode == 0 else 2 * c
                if n <= MAX_LEN:
                    if mode == 0:
                        items = [_fresh(items[i % len(items)], i) for i in range(n)]
                    else:
                        items = [items[i % len(items)] for i in range(n)]
            return items
        return v

    return [walk(a, 0) for a in args]


def _shape(v, depth=0):
    """Type skeleton: inner lists keep their length, top-level lists may grow."""
    t = type(v)
    if t is list:
        inner = tuple(sorted({_shape(x, depth + 1) for x in v}, key=repr))
        return ("list", None if depth <= 1 else len(v), inner)
    return t.__name__


def _same_shape(base, variant):
    if len(base) != len(variant):
        return False
    for b, v in zip(base, variant, strict=False):
        sb, sv = _shape(b, 1), _shape(v, 1)
        if sb == sv:
            continue
        # A grown or shrunk top-level list is fine if its element shapes are ones the base had.
        if type(b) is list and type(v) is list:
            if not b or set(sv[2]) <= set(sb[2]):
                continue
        return False
    return True


def _safe(pred, args):
    try:
        return bool(pred(*args))
    except Exception:
        return False


def _combos(base, own_i, own_s, cap=300):
    """Own constants combined: list lengths x int values x first-element literal.

    Catches conjunctions such as ``len(items) == 13 and limit == 3 and
    items[0] == "A"`` that no single-leaf change reaches.
    """
    lens = [c for c in own_i if 0 < c <= MAX_LEN][:12]
    vals = own_i[:12]
    lits = own_s[:8] + [None]
    tops = [i for i, a in enumerate(base) if type(a) is list and a]
    ints = [i for i, a in enumerate(base) if type(a) is int]
    out = []
    if not (tops or ints):
        return out
    for n in lens or [None]:
        for v in vals or [None]:
            for lit in lits:
                args = list(base)
                for i in tops:
                    if n is not None:
                        args[i] = [args[i][j % len(args[i])] for j in range(n)]
                    if lit is not None and type(args[i][0]) is str:
                        args[i] = [lit] + args[i][1:]
                for i in ints:
                    if v is not None:
                        args[i] = v
                out.append(args)
                if len(out) >= cap:
                    return out
    return out


def variants(bases, source, rng, budget=400, domain=None):
    """Transformed argument lists aimed at the candidate's constants.

    Variants built from the candidate's own literals come first; the ladder
    and rare characters fill the remaining budget.
    """
    ints, strs = harvest(source)
    own_i, own_s = ints[:40], strs[:20]
    ladder = [c for c in LADDER_INTS if c not in ints]
    rare = [ch for ch in RARE_CHARS if ch not in strs]
    # Variants are grouped by (tier, strategy). The budget is shared round-robin
    # across groups in tier order, so a strategy with few but sharp variants
    # (twins differing only past a cap) is never crowded out by a prolific one.
    # Tiers: 0 exact own literals, 1 other own-constant variants, 2 generic
    # shifts and joints, 3 every other generic variant.
    groups = {}
    seen = set()

    def add(tier, base, args, family="?"):
        if not _same_shape(base, args) or (domain is not None and not _safe(domain, args)):
            return
        key = repr(args)
        if key not in seen and len(key) < 200_000:
            seen.add(key)
            groups.setdefault((tier, family), []).append(args)

    for base in bases[:8]:
        for v in _combos(base, own_i, own_s):
            add(0, base, v, "combo")
    for base in bases:
        leaves = list(_leaves(base))
        int_paths = [p for p, leaf in leaves if type(leaf) is int]
        for own, cs, lits in ((True, own_i, own_s), (False, ladder, rare)):
            exact, other, joint = (0, 1, 1) if own else (3, 3, 2)
            for path, leaf in leaves:
                t = type(leaf)
                if t is int:
                    for c in cs:
                        add(exact, base, _replace(base, path, c), "int")
                        for v in _int_values(c):
                            add(other, base, _replace(base, path, v), "int-near")
                elif t is str:
                    for lit in lits:
                        add(exact, base, _replace(base, path, lit), "str")
                        for v in _str_variants(leaf, lit=lit):
                            add(other, base, _replace(base, path, v), "str-lit")
                    for c in cs:
                        for v in _str_variants(leaf, c=c):
                            add(other, base, _replace(base, path, v), "str-len")
                elif t is list and len(path) == 1:
                    # Only stretch top-level list arguments: inner lists are usually
                    # fixed-shape records (pairs, rows) and stretching them leaves the domain.
                    for c in cs:
                        for v in _list_variants(leaf, c):
                            add(other, base, _replace(base, path, v), "list-len")
                    for v in _near_duplicates(leaf, lits):
                        add(exact if own else joint, base, _replace(base, path, v), "near-dup")
            for c in cs:
                # Shift every int leaf by c: keeps orderings such as a <= b intact.
                if int_paths:
                    shifted = base
                    for p in int_paths:
                        cur = shifted
                        for k in p:
                            cur = cur[k]
                        shifted = _replace(shifted, p, cur + c)
                    add(joint, base, shifted, "shift")
                for mode in (0, 1):
                    add(joint, base, _joint(base, c, mode), "joint")
                # Same segment growth on every string leaf, then make the tails differ.
                str_paths = [p for p, leaf in leaves if type(leaf) is str]
                if len(str_paths) >= 2:
                    first = base
                    for k in str_paths[0]:
                        first = first[k]
                    g = _segment_variants(first, c)
                    if g:
                        # Every string leaf gets the same grown value, then the tails differ.
                        same = base
                        for p in str_paths:
                            same = _replace(same, p, g[0])
                        add(joint, base, same, "twin")
                        for i, p in enumerate(str_paths[:2]):
                            for sep in SEPARATORS:
                                if sep in g[0]:
                                    add(joint, base, _replace(same, p, g[0] + sep + str(2 + i)), "twin")
                                    break
    order = sorted(groups)
    for k in order:
        rng.shuffle(groups[k])
    out = []
    while len(out) < budget and any(groups[k] for k in order):
        for k in order:
            if groups[k] and len(out) < budget:
                out.append(groups[k].pop())
    return out


def bases_for(contract, fn_name, rng, extra=6):
    spec = contract.function(fn_name)
    bases = [list(e.args) for e in contract.examples if e.fn == fn_name]
    bases += [list(a) for a in spec.args.edges()][:30]
    bases += [list(spec.args.draw(rng, 20)) for _ in range(extra)]
    return bases


def seeded(seed):
    return random.Random(seed ^ 0x7A7A)
