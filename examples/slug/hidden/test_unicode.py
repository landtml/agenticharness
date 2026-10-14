from slug import slugify


def test_accents():
    assert slugify("Crème Brûlée") == "creme-brulee"


def test_no_ascii_form_dropped():
    assert slugify("Ærø") == "r"
