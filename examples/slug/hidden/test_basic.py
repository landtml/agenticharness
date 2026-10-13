from slug import slugify


def test_basic():
    assert slugify("Hello, World!") == "hello-world"


def test_collapse_and_strip():
    assert slugify("  --A  b--  ") == "a-b"


def test_empty():
    assert slugify("") == ""


def test_digits():
    assert slugify("Route 66") == "route-66"
