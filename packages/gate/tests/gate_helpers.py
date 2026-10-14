import os
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))

from urh_gate import load_contract  # noqa: E402

PRACTICE = os.path.join(HERE, "fixtures", "practice", "hidden", "contract.py")
PRACTICE_REF = os.path.join(HERE, "fixtures", "practice", "hidden", "reference.py")


def practice():
    return load_contract(PRACTICE)


def workspace(source, name="solution.py"):
    d = tempfile.mkdtemp(prefix="urh-test-")
    if source is not None:
        with open(os.path.join(d, name), "w") as fh:
            fh.write(source)
    return d


with open(PRACTICE_REF) as _fh:
    CORRECT = _fh.read()
