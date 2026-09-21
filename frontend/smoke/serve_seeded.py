"""The real service with one project and two analysed drawings, so the signed-in side can be clicked.

    python frontend/smoke/serve_seeded.py     # serves on 127.0.0.1:8077, writes ui/job.txt, then waits
    python frontend/smoke/ui_smoke.py         # clicks through it and reports what the console said

Everything lives in a temporary directory, so nothing here can touch a real database or a real result. The
frontend has to be built first (npm run build); the API serves frontend/dist itself.
""" 
import os, sys, tempfile, threading, time
ROOT = "/home/user/vvs5"
SP = os.environ.get("SP", os.path.dirname(os.path.abspath(__file__)))
tmp = tempfile.mkdtemp(prefix="ui-")
os.environ["VVS_DATABASE_URL"] = f"sqlite:///{tmp}/ui.db"
os.environ["VVS_STORAGE_ROOT"] = f"{tmp}/storage"
os.environ["VVS_SECRET_KEY"] = "ui"
os.environ["VVS_SECOND_READER"] = "false"
sys.path.insert(0, os.path.join(ROOT, "backend")); sys.path.insert(0, os.path.join(ROOT, "engine"))
import socket
import uvicorn
from app.main import app
# En äldre instans som håller porten är ett fel att stanna på, inte att prata förbi: annars seedar den här sin
# egen databas och skriver ett token som porten aldrig känner till, och rökprovet hittar inga projekt.
with socket.socket() as probe:
    if probe.connect_ex(("127.0.0.1", 8077)) == 0:
        raise SystemExit("port 8077 är upptagen - stoppa den gamla seedade tjänsten först (pkill -f serve_seeded)")
threading.Thread(target=lambda: uvicorn.run(app, host="127.0.0.1", port=8077, log_level="warning"), daemon=True).start()
time.sleep(2)
from fastapi.testclient import TestClient
with TestClient(app) as c:
    tok = c.post("/api/auth/register", json={"email": "ui@example.com", "password": "hemligt1"}).json()["access_token"]
    H = {"Authorization": f"Bearer {tok}"}
    p = c.post("/api/projects", json={"name": "Kv Bjorken, hus A", "description": "VVS-plan, tre blad"}, headers=H).json()
    job = ""
    for tag, nm in (("A", "268140-W-50-P-A-00 VVS PLAN 2.pdf"), ("C", "268140-W-50-P-A-01 VVS PLAN 3.pdf")):
        # facit-ritningarna ligger utanför repot; på en ren klon finns bara utvecklingsritningarna, och de duger
        src = f"{ROOT}/data/validation_{tag}/clean.pdf"
        if not os.path.exists(src):
            src = f"{ROOT}/data/dev/DRAWING_{tag}.pdf"
        with open(src, "rb") as fh:
            d = c.post(f"/api/projects/{p['id']}/drawings", files={"file": (nm, fh, "application/pdf")}, headers=H).json()
        j = c.post(f"/api/drawings/{d['id']}/analyze", headers=H).json()
        for _ in range(600):
            j = c.get(f"/api/jobs/{j['id']}", headers=H).json()
            if j["status"] in ("COMPLETED", "FAILED"): break
            time.sleep(0.5)
        print(tag, j["status"], flush=True)
        if tag == "A": job = j["id"]
os.makedirs(f"{SP}/ui", exist_ok=True) or open(f"{SP}/ui/job.txt", "w").write(f"{job} {tok}")
print("READY", flush=True)
while True: time.sleep(3600)
