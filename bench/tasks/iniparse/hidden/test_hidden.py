import pytest
from iniparse import parse


def test_sections_and_entries():
    assert parse("[a]\nx=1\ny : 2\n") == {"a": {"x": "1", "y": "2"}}


def test_default_and_comments():
    t = "top=1\n; c\n  # c2\n\n[S]\nk=v\n"
    assert parse(t) == {"DEFAULT": {"top": "1"}, "S": {"k": "v"}}


def test_first_separator_wins():
    assert parse("[s]\nurl = http://x:80/a=b\n") == {"s": {"url": "http://x:80/a=b"}}
    assert parse("[s]\nk: a=b\n") == {"s": {"k": "a=b"}}


def test_lowercase_keys_case_kept_sections():
    assert parse("[MySec]\nKEY=V\n") == {"MySec": {"key": "V"}}


def test_repeats():
    assert parse("[s]\nk=1\n[t]\nz=0\n[s]\nk=2\nj=3\n") == {"s": {"k": "2", "j": "3"}, "t": {"z": "0"}}


def test_header_whitespace():
    assert parse("  [ s ]  \nk=v") == {"s": {"k": "v"}}


def test_bad_line_reports_line_number():
    with pytest.raises(ValueError, match="3"):
        parse("[s]\nk=v\nnot an entry\n")
