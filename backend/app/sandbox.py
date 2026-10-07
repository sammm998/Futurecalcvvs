"""Run the code a model wrote, against data handed to it, and nothing else.

The solving agent may write its own Python to look at a drawing it has never seen: group these lines by pen, find
the ones that run parallel to that label, measure the gap between two ends. That code comes from a model, and the
model has read text off a customer's drawing, so it is treated as hostile however it reads. Four walls:

  * the source is parsed first, and anything that reaches outside the data is refused before it runs: imports
    other than a short list of pure calculation modules, dunder attributes, and the builtins that open files,
    compile code or reach the interpreter;
  * it runs in its own interpreter process (`python -I`), with an empty environment - no key, no token, no path
    to the service's data - in a fresh temporary directory;
  * that process is held to a CPU time, a memory ceiling, no child processes and no file larger than a few
    megabytes, and is killed on a wall-clock deadline;
  * the data goes in on stdin and the answer comes out on stdout as JSON, capped in size. The code gets no handle
    on the database, the storage, the network clients or the correction log.

None of these alone makes Python safe, and together they still are not a proof. What the code can do at worst is
compute something wrong, and what it computes is only ever read by the agent, never written into a takeoff: every
metre that reaches the quantity is measured again by the engine's own tools.
"""
from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
import tempfile

ALLOWED_IMPORTS = {"math", "statistics", "itertools", "collections", "json", "re", "functools", "operator",
                   "numpy", "shapely", "shapely.geometry", "shapely.ops", "shapely.strtree", "heapq", "bisect"}
FORBIDDEN_NAMES = {"open", "exec", "eval", "compile", "__import__", "input", "breakpoint", "globals", "locals",
                   "vars", "getattr", "setattr", "delattr", "memoryview", "help", "exit", "quit", "os", "sys",
                   "subprocess", "socket", "importlib", "builtins", "ctypes", "pickle", "marshal", "io", "pathlib",
                   "shutil", "signal", "threading", "multiprocessing", "type", "object", "super", "classmethod",
                   "staticmethod", "property"}
CPU_SECONDS = 20
WALL_SECONDS = 30
MEMORY_BYTES = 1024 * 1024 * 1024
MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_OUTPUT_CHARS = 200_000
MAX_CODE_CHARS = 20_000


class Refused(ValueError):
    """The code was not run: it reaches for something outside the data."""


def check(code: str) -> None:
    """Refuse code that reaches outside the data, before it runs."""
    if len(code) > MAX_CODE_CHARS:
        raise Refused(f"koden är för lång ({len(code)} tecken, högst {MAX_CODE_CHARS})")
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        raise Refused(f"syntaxfel: {exc.msg} på rad {exc.lineno}") from exc
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name not in ALLOWED_IMPORTS:
                    raise Refused(f"import av {a.name} är inte tillåten")
        elif isinstance(node, ast.ImportFrom):
            if (node.module or "") not in ALLOWED_IMPORTS or node.level:
                raise Refused(f"import från {node.module} är inte tillåten")
        elif isinstance(node, ast.Attribute):
            if node.attr.startswith("__") or node.attr.startswith("_"):
                raise Refused(f"attributet {node.attr} är inte tillåtet")
        elif isinstance(node, ast.Name):
            if node.id in FORBIDDEN_NAMES or node.id.startswith("__"):
                raise Refused(f"namnet {node.id} är inte tillåtet")
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            raise Refused("global och nonlocal är inte tillåtna")
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and "__" in node.value:
            raise Refused("strängar med dubbla understreck är inte tillåtna")


# What runs inside the child: limits first, then the builtins narrowed, then the code with the data as globals.
_RUNNER = r'''
import json, resource, sys
resource.setrlimit(resource.RLIMIT_CPU, (%(cpu)d, %(cpu)d))
resource.setrlimit(resource.RLIMIT_AS, (%(mem)d, %(mem)d))
resource.setrlimit(resource.RLIMIT_FSIZE, (%(fsize)d, %(fsize)d))
try:
    resource.setrlimit(resource.RLIMIT_NPROC, (0, 0))
except (ValueError, OSError):
    pass
import math, statistics, itertools, collections, functools, operator, re, heapq, bisect
import numpy
import shapely, shapely.geometry, shapely.ops, shapely.strtree
payload = json.loads(sys.stdin.read())
real_import = __builtins__.__import__ if hasattr(__builtins__, "__import__") else __import__
ALLOWED = set(payload["allowed"])
def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
    if name not in ALLOWED:
        raise ImportError("import av " + name + " är inte tillåten")
    return real_import(name, globals, locals, fromlist, level)
import builtins as _b
safe = {k: getattr(_b, k) for k in ("abs", "all", "any", "bool", "dict", "enumerate", "filter", "float",
        "frozenset", "int", "isinstance", "len", "list", "map", "max", "min", "print", "range", "repr",
        "reversed", "round", "set", "sorted", "str", "sum", "tuple", "zip", "Exception", "ValueError",
        "KeyError", "IndexError", "TypeError", "ZeroDivisionError", "StopIteration", "divmod", "pow", "hash",
        "iter", "next", "slice", "chr", "ord", "hex", "bin", "format", "callable", "hasattr", "issubclass",
        "NotImplementedError", "ArithmeticError", "True", "False", "None") if hasattr(_b, k)}
safe["__import__"] = guarded_import
env = {"__builtins__": safe, "math": math, "statistics": statistics, "itertools": itertools,
       "collections": collections, "re": re, "json": json, "numpy": numpy, "np": numpy, "shapely": shapely,
       "result": None}
env.update(payload["data"])
exec(compile(payload["code"], "<agent>", "exec"), env)
out = env.get("result")
sys.stdout.write("\n@@RESULT@@" + json.dumps(out, default=str))
'''


def run(code: str, data: dict) -> dict:
    """Run `code` with `data` as its globals. The code puts its answer in `result`. Returns
    {"ok": True, "result": ..., "printed": "..."} or {"ok": False, "error": "..."}."""
    try:
        check(code)
    except Refused as exc:
        return {"ok": False, "error": f"Koden kördes inte: {exc}"}
    runner = _RUNNER % {"cpu": CPU_SECONDS, "mem": MEMORY_BYTES, "fsize": MAX_FILE_BYTES}
    payload = json.dumps({"code": code, "data": data, "allowed": sorted(ALLOWED_IMPORTS)}, default=str)
    with tempfile.TemporaryDirectory(prefix="vvs-agent-") as work:
        try:
            p = subprocess.run([sys.executable, "-I", "-c", runner], input=payload, capture_output=True,
                               text=True, timeout=WALL_SECONDS, cwd=work,
                               env={"PATH": "/usr/bin:/bin", "HOME": work, "OPENBLAS_NUM_THREADS": "1",
                                    "OMP_NUM_THREADS": "1"})
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": f"Koden tog längre än {WALL_SECONDS} s och stoppades."}
    out = p.stdout or ""
    if "\n@@RESULT@@" not in out:
        err = (p.stderr or "").strip().splitlines()
        tail = err[-1] if err else f"processen avslutades med kod {p.returncode}"
        return {"ok": False, "error": f"Koden föll: {tail[:500]}", "printed": out[-2000:]}
    printed, _, raw = out.rpartition("\n@@RESULT@@")
    if len(raw) > MAX_OUTPUT_CHARS:
        return {"ok": False, "error": f"Svaret var för stort ({len(raw)} tecken); sammanfatta i koden."}
    try:
        result = json.loads(raw)
    except ValueError:
        return {"ok": False, "error": "Svaret gick inte att läsa som JSON."}
    return {"ok": True, "result": result, "printed": printed[-4000:]}
