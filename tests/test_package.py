import urh


def test_version_is_set():
    assert urh.__version__
    assert urh.HARNESS_VERSION == urh.__version__
