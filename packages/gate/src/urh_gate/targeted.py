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
import unicodedata

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


class _NotConst(Exception):
    pass


_FOLD_CALLS = {"len": len, "sum": sum, "abs": abs, "min": min, "max": max, "chr": chr, "ord": ord}
_FOLD_OPS = {
    ast.Add: lambda a, b: a + b,
    ast.Sub: lambda a, b: a - b,
    ast.Mult: lambda a, b: a * b,
    ast.FloorDiv: lambda a, b: a // b,
    ast.Mod: lambda a, b: a % b,
    ast.Pow: lambda a, b: a**b,
}


def _fold(node, depth=0):
    """Value of a constant expression such as ``len("abcdefg")`` or ``sum((3, 4))``.

    Thresholds hidden behind a computation are as easy to write as plain
    literals, so the harvest evaluates small pure expressions over constants.
    """
    if depth > 8:
        raise _NotConst
    if isinstance(node, ast.Constant) and type(node.value) in (int, str):
        if type(node.value) is str and len(node.value) > 200:
            raise _NotConst
        return node.value
    if isinstance(node, (ast.Tuple, ast.List)):
        if len(node.elts) > 50:
            raise _NotConst
        return tuple(_fold(e, depth + 1) for e in node.elts)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        v = _fold(node.operand, depth + 1)
        if type(v) is not int:
            raise _NotConst
        return -v if isinstance(node.op, ast.USub) else v
    if isinstance(node, ast.BinOp) and type(node.op) in _FOLD_OPS:
        a, b = _fold(node.left, depth + 1), _fold(node.right, depth + 1)
        if isinstance(node.op, ast.Pow):
            if not (type(a) is int and type(b) is int and abs(a) <= 1 << 16 and 0 <= b <= 70):
                raise _NotConst
        elif isinstance(node.op, ast.Mult) and (type(a) is str or type(b) is str):
            if not (type(a) is int and a <= 64) and not (type(b) is int and b <= 64):
                raise _NotConst
        try:
            return _FOLD_OPS[type(node.op)](a, b)
        except Exception as e:
            raise _NotConst from e
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _FOLD_CALLS:
        if node.keywords:
            raise _NotConst
        args = [_fold(a, depth + 1) for a in node.args]
        try:
            return _FOLD_CALLS[node.func.id](*args)
        except Exception as e:
            raise _NotConst from e
    raise _NotConst


def harvest(source):
    """Ints and short strings the candidate names, as literals or constant expressions."""
    ints, strs = set(), set()
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return [], []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Constant, ast.UnaryOp, ast.BinOp, ast.Call)):
            continue
        try:
            v = _fold(node)
        except (_NotConst, RecursionError):
            continue
        if type(v) is int:
            near = (v - 1, v, v + 1) if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Pow) else (v,)
            ints.update(x for x in near if 2 <= abs(x) <= MAX_CONST)
        elif type(v) is str and 0 < len(v) <= 40:
            strs.add(v)
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
        out += _run_variants(s, c)
    if lit is not None and len(lit) == 1:
        out += [lit * 2, lit * 3, s + lit * 2]
    return out


SEPARATORS = ".", "/", ",", ";", " ", "-", ":"


def _bump(ch):
    if ch.isdigit():
        return "0123456789"[(int(ch) + 1) % 10] if ch in "0123456789" else "1"
    if "a" <= ch < "z" or "A" <= ch < "Z":
        return chr(ord(ch) + 1)
    return "a"


def _near_twins(s):
    """Strings one small step from ``s``: same text, last character bumped, a separator
    suffix cut off, or a separator suffix added."""
    out = [s]
    if s:
        out.append(s[:-1] + _bump(s[-1]))
    for sep in SEPARATORS + ("+",):
        if sep in s:
            out.append(s.split(sep, 1)[0])
            out.append(s.rsplit(sep, 1)[0])
    out += [s + "+b", s + "+b.1", s + "-a", s + ".0"]
    seen, uniq = set(), []
    for t in out:
        if t not in seen:
            seen.add(t)
            uniq.append(t)
    return uniq


def _run_variants(s, c, ks=(1, 2, 3, 4)):
    """Strings made of k runs of length c each, drawn from the leaf's own characters."""
    chars = list(dict.fromkeys(s)) or ["a"]
    if len(chars) < 4:
        chars += [ch for ch in "abcd" if ch not in chars]
    out = []
    if 0 < c <= 512:
        for k in ks:
            out.append("".join(chars[i % len(chars)] * c for i in range(k)))
    return out


def _segment_variants(s, c):
    """Grow the number of separator-delimited segments to about c."""
    out = []
    for sep in SEPARATORS:
        if sep in s and 0 < c <= 10_000:
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
        unicodedata.normalize("NFD", e + "\u00e9"),
        e + "\u00e9",
        unicodedata.normalize("NFKC", e) if unicodedata.normalize("NFKC", e) != e else e + "\ufb01",
    ]
    copies += [lit + e for lit in lits[:6]] + [e + lit for lit in lits[:6]]
    for c in copies:
        if c != e:
            out.append(lst + [c])
            out.append([c] + lst)
    # Canonically equivalent but different strings, both present: exact keys must stay apart.
    composed = e + "\u00e9"
    out.append(lst + [composed, unicodedata.normalize("NFD", composed), composed])
    return out


def _joint(args, c, mode):
    """Apply one constant to every leaf at once (thresholds that need two conditions)."""

    def walk(v, depth):
        t = type(v)
        if t is int:
            return c if mode == 0 else c + 1  # mode 2: one over the limit, with room to exceed it
        if t is str:
            if not v or c > MAX_LEN or mode == 2:
                return v
            if mode == 0:
                return " ".join([v] * max(1, (c + 1) // (len(v) + 1) + 1))
            return (v * ((c + 1) // len(v) + 1))[: c + 1]
        if t is list:
            items = [walk(x, depth + 1) for x in v]
            if depth == 0 and items and c < MAX_LEN:
                n = (c + 1, 2 * c, c + 2)[mode]
                if n <= MAX_LEN:
                    if mode != 1:
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
                for mode in (0, 1, 2):
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
                        for sep in SEPARATORS:
                            if sep in g[0]:
                                for i, p in enumerate(str_paths[:2]):
                                    add(joint, base, _replace(same, p, g[0] + sep + str(2 + i)), "twin")
                                # Both grown past the constant, differing only at the very end.
                                both = _replace(same, str_paths[0], g[0] + sep + "2")
                                add(joint, base, _replace(both, str_paths[1], g[0] + sep + "3"), "twin")
                                break
                        for t in _near_twins(g[0])[1:]:
                            pair = _replace(_replace(base, str_paths[0], g[0]), str_paths[1], t)
                            add(joint, base, pair, "twin-near")
        # Pairs that are nearly equal: a comparison must treat them exactly as the spec says,
        # whatever metadata, suffix or last character tells them apart.
        str_paths = [p for p, leaf in leaves if type(leaf) is str]
        if len(str_paths) >= 2:
            first = base
            for k in str_paths[0]:
                first = first[k]
            for twin in _near_twins(first):
                for a_val, b_val in ((first, twin), (twin, first)):
                    pair = _replace(_replace(base, str_paths[0], a_val), str_paths[1], b_val)
                    add(2, base, pair, "pair")
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
