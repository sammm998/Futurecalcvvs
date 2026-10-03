"""The owner asked for the service to start over from nothing. It happens once, and never again."""
import os
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

SCRIPT = r"""
import os, sys
sys.path.insert(0, os.path.join(sys.argv[1], "backend"))
from app.db import SessionLocal, User, init_db
from app import reset_once
init_db()
store = sys.argv[2]
os.makedirs(os.path.join(store, "results", "d"), exist_ok=True)
open(os.path.join(store, "results", "d", "q.json"), "w").write("{}")
with SessionLocal() as db:
    db.add(User(email="a@example.com", password_hash="x", role="admin")); db.commit()
first = reset_once.run(store)
with SessionLocal() as db:
    users_after_first = db.query(User).count()
os.makedirs(os.path.join(store, "results"), exist_ok=True)
with SessionLocal() as db:
    db.add(User(email="b@example.com", password_hash="x", role="admin")); db.commit()
second = reset_once.run(store)
with SessionLocal() as db:
    users_after_second = db.query(User).count()
print(first, users_after_first, os.listdir(store) if False else "", second, users_after_second)
"""


def test_the_reset_empties_everything_once_and_then_never_again(tmp_path):
    env = dict(os.environ, VVS_DATABASE_URL=f"sqlite:///{tmp_path}/t.db", VVS_STORAGE_ROOT=str(tmp_path / "store"),
               VVS_SECRET_KEY="x" * 40)
    env.pop("PYTEST_CURRENT_TEST", None)
    out = subprocess.run([sys.executable, "-c", SCRIPT, ROOT, str(tmp_path / "store")], env=env,
                         capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr
    first, n1, second, n2 = out.stdout.split()[-4:] if len(out.stdout.split()) >= 4 else out.stdout.split()
    assert first == "True" and n1 == "0"            # everything gone the first time
    assert second == "False" and n2 == "1"          # the account made afterwards survives the next start
