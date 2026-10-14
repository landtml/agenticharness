import subprocess
import sys

import pytest
from rpn import evaluate


def test_ops():
    assert evaluate("3 4 +") == 7
    assert evaluate("10 4 -") == 6
    assert evaluate("2 3 ^") == 8
    assert evaluate("7 2 /") == 3.5
    assert evaluate("-3.5 neg") == 3.5
    assert evaluate("16 sqrt") == 4


def test_order():
    assert evaluate("5 1 2 + 4 * + 3 -") == 14


@pytest.mark.parametrize("bad", ["", "1 0 /", "-4 sqrt", "1 x +", "+", "1 2"])
def test_errors(bad):
    with pytest.raises(ValueError):
        evaluate(bad)


def test_cli():
    ok = subprocess.run([sys.executable, "rpn.py", "3 4 +"], capture_output=True, text=True)
    assert ok.returncode == 0 and ok.stdout.strip() == "7"
    half = subprocess.run([sys.executable, "rpn.py", "7 2 /"], capture_output=True, text=True)
    assert half.stdout.strip() == "3.5"
    bad = subprocess.run([sys.executable, "rpn.py", "1 0 /"], capture_output=True, text=True)
    assert bad.returncode == 1 and bad.stderr.strip()
