import os
import subprocess
import sys

import pytest
from kv.query import execute
from kv.store import Store


def test_put_get_delete(tmp_path):
    s = Store(str(tmp_path / "db"))
    s.put("a", "1")
    s.put("b", "two words")
    assert s.get("a") == "1" and s.get("b") == "two words"
    s.delete("a")
    s.delete("missing")
    assert s.get("a") is None
    s.close()


def test_persistence_and_overwrite(tmp_path):
    p = str(tmp_path / "db")
    s = Store(p)
    s.put("k", "v1")
    s.put("k", "v2")
    s.put("gone", "x")
    s.delete("gone")
    s.close()
    s2 = Store(p)
    assert s2.get("k") == "v2" and s2.get("gone") is None
    s2.close()


def test_writes_are_flushed_without_close(tmp_path):
    p = str(tmp_path / "db")
    s = Store(p)
    s.put("x", "1")
    assert Store(p).get("x") == "1"


def test_keys_prefix_sorted(tmp_path):
    s = Store(str(tmp_path / "db"))
    for k in ["user:2", "user:1", "item:1", "user:10"]:
        s.put(k, "v")
    s.delete("user:2")
    assert s.keys() == ["item:1", "user:1", "user:10"]
    assert s.keys("user:") == ["user:1", "user:10"]
    assert s.keys("zzz") == []


def test_truncated_last_line_ignored(tmp_path):
    p = str(tmp_path / "db")
    s = Store(p)
    s.put("a", "1")
    s.close()
    with open(p, "a") as f:
        f.write('{"op": "put", "ke')
    assert Store(p).get("a") == "1"


def test_corrupt_middle_line_raises_with_line_number(tmp_path):
    p = str(tmp_path / "db")
    s = Store(p)
    s.put("a", "1")
    s.close()
    lines = open(p).read().splitlines()
    with open(p, "w") as f:
        f.write(lines[0] + "\n" + "garbage\n" + lines[0] + "\n")
    with pytest.raises(ValueError, match="2"):
        Store(p)


def test_compact_keeps_live_keys_only(tmp_path):
    p = str(tmp_path / "db")
    s = Store(p)
    for i in range(20):
        s.put("k", str(i))
    s.put("other", "o")
    s.put("dead", "d")
    s.delete("dead")
    s.compact()
    assert len([ln for ln in open(p).read().splitlines() if ln.strip()]) == 2
    assert s.get("k") == "19"
    s.put("after", "1")
    s.close()
    s2 = Store(p)
    assert (
        s2.get("k") == "19" and s2.get("other") == "o" and s2.get("after") == "1" and s2.get("dead") is None
    )
    assert not [f for f in os.listdir(tmp_path) if f != "db"]


def test_query_commands(tmp_path):
    s = Store(str(tmp_path / "db"))
    assert execute(s, "SET greeting hello world") == "OK"
    assert execute(s, "get greeting") == "hello world"
    assert execute(s, "GET Greeting") == "(nil)"
    assert execute(s, "SET b 1") == "OK"
    assert execute(s, "KEYS") == "b\ngreeting"
    assert execute(s, "KEYS g") == "greeting"
    assert execute(s, "KEYS z") == ""
    assert execute(s, "DEL b") == "OK"
    assert execute(s, "COMPACT") == "OK"
    assert execute(s, "KEYS") == "greeting"


@pytest.mark.parametrize("bad", ["FROB x", "GET", "SET onlykey", "DEL", "GET a b", ""])
def test_query_errors(tmp_path, bad):
    s = Store(str(tmp_path / "db"))
    with pytest.raises(ValueError):
        execute(s, bad)


def test_cli(tmp_path):
    db = str(tmp_path / "db")
    script = "SET a 1\nGET a\nNOPE\nGET missing\n"
    r = subprocess.run(
        [sys.executable, "-m", "kv", db],
        input=script,
        capture_output=True,
        text=True,
        cwd=os.getcwd(),
        timeout=60,
    )
    assert r.returncode == 0
    out = r.stdout.splitlines()
    assert out[0] == "OK" and out[1] == "1" and out[2].startswith("ERR ") and out[3] == "(nil)"
    r2 = subprocess.run(
        [sys.executable, "-m", "kv", db], input="GET a\n", capture_output=True, text=True, timeout=60
    )
    assert r2.stdout.strip() == "1"
