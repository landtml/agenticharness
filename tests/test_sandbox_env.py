import subprocess

from urh import sandbox


def test_python3_in_the_scrubbed_env_has_the_harness_packages(tmp_path):
    """Plan checks and workers run `python3 -m pytest`; inside a virtualenv that must reach its packages."""
    env = sandbox.scrubbed_env(str(tmp_path))
    r = subprocess.run(["python3", "-c", "import pytest"], env=env, capture_output=True, cwd=tmp_path)
    assert r.returncode == 0, r.stderr
