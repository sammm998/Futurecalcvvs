"""The agent's own code runs walled off: it can compute over the data it is given and reach nothing else."""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend")))
from app import sandbox  # noqa: E402


def test_code_computes_over_the_data_it_is_given():
    out = sandbox.run("from shapely.geometry import LineString\n"
                      "result = round(sum(LineString([(s['x0'], s['y0']), (s['x1'], s['y1'])]).length for s in segs) * mpp, 3)",
                      {"segs": [{"x0": 0, "y0": 0, "x1": 3, "y1": 4}, {"x0": 0, "y0": 0, "x1": 0, "y1": 10}], "mpp": 0.1})
    assert out == {"ok": True, "result": 1.5, "printed": ""}


def test_code_that_reaches_outside_is_refused_before_it_runs():
    for code in ("import os", "import subprocess", "from pathlib import Path", "open('/etc/passwd')",
                 "x = ().__class__.__bases__", "eval('1')", "__import__('os')", "getattr(segs, 'x')",
                 "s = '__class__'", "import socket"):
        out = sandbox.run(code, {"segs": []})
        assert not out["ok"] and "kördes inte" in out["error"], code


def test_a_runaway_is_stopped():
    assert not sandbox.run("while True:\n    pass", {})["ok"]
    assert not sandbox.run("a = [0] * (10 ** 10)", {})["ok"]


def test_the_environment_carries_no_secret():
    os.environ["SECRET_FOR_TEST"] = "x"
    try:
        out = sandbox.run("result = 1", {})
        assert out["ok"]
        assert not sandbox.run("import os\nresult = os.environ", {})["ok"]
    finally:
        os.environ.pop("SECRET_FOR_TEST")
