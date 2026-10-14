from slug import slugify

def test_basic():
    assert slugify("Hello, World!") == "hello-world"

def test_accents():
    assert slugify("Crème Brûlée") == "creme-brulee"

def test_runs_and_ends():
    assert slugify("  --a__b  c--  ") == "a-b-c"

def test_separator():
    assert slugify("A b C", separator="_") == "a_b_c"

def test_empty():
    assert slugify("") == ""
    assert slugify("!!!") == ""

def test_digits_and_non_ascii_dropped():
    assert slugify("Room 101 → 日本") == "room-101"
