import json
import math
import subprocess
import sys

import pytest
from minijson import JSONError, dumps, loads, resolve


@pytest.mark.parametrize(
    "text",
    [
        '{"a": [1, 2.5, -3e2, true, false, null], "b": {"c": "d"}}',
        "  [ ]  ",
        "{}",
        '"\\u00e9\\n\\t\\\\\\"\\/"',
        '"\\ud83d\\ude00"',
        "0",
        "-0.0",
        "1E+3",
        "[[[[[]]]]]",
        '{"nested": {"deep": [{"x": 1}, {"y": [null]}]}}',
    ],
)
def test_loads_matches_stdlib(text):
    got = loads(text)
    want = json.loads(text)
    assert got == want and type(got) is type(want)


def test_number_types():
    assert type(loads("10")) is int and type(loads("1.0")) is float and type(loads("1e2")) is float


@pytest.mark.parametrize(
    "bad", ["", "[1, 2,]", "{'a': 1}", "01", '"a\nb"', "[1] x", '{"a" 1}', "tru", "[", '{"a":1,}', "-", "1."]
)
def test_loads_rejects(bad):
    with pytest.raises(JSONError):
        loads(bad)


def test_error_is_value_error_with_position():
    assert issubclass(JSONError, ValueError)
    with pytest.raises(JSONError, match="line 2 column 3"):
        loads("[1,\n  x]")


@pytest.mark.parametrize(
    "value",
    [
        {"a": [1, 2.5, None, True, False], "b": "é☃", "c": {}},
        [],
        'tab\there "quoted" back\\slash',
        "😀",
        {"z": 1, "a": {"y": [], "b": [1, [2, {}]]}},
        1.5e-7,
    ],
)
def test_dumps_matches_stdlib(value):
    assert dumps(value) == json.dumps(value)
    assert dumps(value, indent=2) == json.dumps(value, indent=2)
    assert dumps(value, indent=4, sort_keys=True) == json.dumps(value, indent=4, sort_keys=True)
    assert loads(dumps(value)) == value


def test_dumps_rejects():
    with pytest.raises(ValueError):
        dumps(math.nan)
    with pytest.raises(ValueError):
        dumps([math.inf])
    with pytest.raises(TypeError):
        dumps({1: "x"})


def test_pointer():
    doc = {"foo": ["bar", "baz"], "": 0, "a/b": 1, "m~n": 8, " ": 7}
    assert resolve(doc, "") is doc
    assert resolve(doc, "/foo") == ["bar", "baz"]
    assert resolve(doc, "/foo/0") == "bar"
    assert resolve(doc, "/") == 0
    assert resolve(doc, "/a~1b") == 1
    assert resolve(doc, "/m~0n") == 8
    assert resolve(doc, "/ ") == 7
    for bad in ["/nope", "/foo/2", "/foo/01", "/foo/-1"]:
        with pytest.raises(KeyError):
            resolve(doc, bad)


def test_cli():
    r = subprocess.run(
        [sys.executable, "-m", "minijson", "--indent", "2", "--sort-keys"],
        input='{"b": 1, "a": [true]}',
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert r.returncode == 0
    assert r.stdout.strip() == json.dumps({"b": 1, "a": [True]}, indent=2, sort_keys=True)
    r = subprocess.run(
        [sys.executable, "-m", "minijson"], input="[1,", capture_output=True, text=True, timeout=60
    )
    assert r.returncode == 1 and "line 1" in r.stderr


def test_no_json_import():
    import pathlib

    import minijson

    root = pathlib.Path(minijson.__file__).parent
    for f in root.rglob("*.py"):
        src = f.read_text()
        assert "import json" not in src and "from json" not in src
