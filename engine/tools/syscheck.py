"""Walk the whole system as a user does and report the first thing that is not right."""
import json, os, sys, tempfile, time, traceback

ROOT = "/home/user/vvs5"
tmp = tempfile.mkdtemp(prefix="syscheck-")
os.environ["VVS_DATABASE_URL"] = f"sqlite:///{tmp}/s.db"
os.environ["VVS_STORAGE_ROOT"] = f"{tmp}/storage"
os.environ["VVS_SECRET_KEY"] = "syscheck"
sys.path.insert(0, os.path.join(ROOT, "backend"))
sys.path.insert(0, os.path.join(ROOT, "engine"))

from fastapi.testclient import TestClient
from app.main import app

FAIL = []
def check(name, ok, detail=""):
    print(f"  {'ok  ' if ok else 'FEL '} {name}{'  ' + str(detail)[:220] if detail else ''}", flush=True)
    if not ok:
        FAIL.append(name)

pdf = sys.argv[1] if len(sys.argv) > 1 else f"{ROOT}/data/validation_A/clean.pdf"
with TestClient(app) as c:
    check("health", c.get("/health").json().get("status") == "ok")
    r = c.post("/api/auth/register", json={"email": "sys@example.com", "password": "hemligt1"})
    check("register", r.status_code == 200, r.text)
    H = {"Authorization": f"Bearer {r.json()['access_token']}"}
    check("login", c.post("/api/auth/login", data={"username": "sys@example.com", "password": "hemligt1"}).status_code == 200)
    p = c.post("/api/projects", json={"name": "Syscheck", "description": ""}, headers=H)
    check("create project", p.status_code == 200, p.text)
    p = p.json()
    check("list projects", len(c.get("/api/projects", headers=H).json()) == 1)
    with open(pdf, "rb") as fh:
        d = c.post(f"/api/projects/{p['id']}/drawings", files={"file": ("a.pdf", fh, "application/pdf")}, headers=H)
    check("upload", d.status_code == 200, d.text)
    d = d.json()
    check("drawing", c.get(f"/api/drawings/{d['id']}", headers=H).status_code == 200)
    j = c.post(f"/api/drawings/{d['id']}/analyze", headers=H)
    check("start analysis", j.status_code == 200, j.text)
    j = j.json()

    saw_film = False
    t0 = time.time()
    for _ in range(2400):
        js = c.get(f"/api/jobs/{j['id']}", headers=H)
        if js.status_code != 200:
            check("job status", False, js.text); break
        js = js.json()
        f = c.get(f"/api/jobs/{j['id']}/film", headers=H)
        if f.status_code == 200 and f.json().get("frames"):
            saw_film = True
        if js["status"] in ("COMPLETED", "FAILED"):
            break
        time.sleep(0.5)
    check("analysis completed", js["status"] == "COMPLETED", (js.get("error") or "")[:200])
    check("film while running", saw_film)
    print(f"      ({round(time.time()-t0,1)} s)")

    res = c.get(f"/api/jobs/{j['id']}/result", headers=H)
    check("result 200", res.status_code == 200, res.text[:400])
    if res.status_code == 200:
        R = res.json()
        for key in ("quantities", "pipes", "designations", "leaders", "anchors", "issues", "coverage",
                    "scale", "totals", "build", "proposals", "corrections"):
            check(f"result has {key}", key in R)
        check("quantities non-empty", bool(R["quantities"]))
        check("build stamped", bool(R.get("build", {}).get("engine")), R.get("build"))
        check("issues have severity", all("severity" in i for i in R["issues"]))
        # every field the takeoff table and its run drill-down actually read
        want_pipe = ("physical_pipe_id", "identity", "page", "supporting_anchors", "graph_nodes",
                     "horizontal_m", "vertical_m", "total_m", "bridged_gap_pt", "reasons", "geometry")
        missing = sorted({k for p in R["pipes"] for k in want_pipe if k not in p})
        check("pipes carry what the table reads", not missing, missing)
        # risers_calc / horizontal_calc / vertical_calc / total_calc are derived in the browser from these,
        # because the floor height is the reader's to give and the engine never assumes one
        want_q = ("designation", "base", "dn", "state", "label_count", "physical_pipe_count",
                  "confirmed_horizontal_m", "confirmed_total_m", "vertical_m", "ambiguous_m",
                  "in_hatched_area_m", "riser_count", "riser_count_from_labels")
        qmiss = sorted({k for q in R["quantities"] for k in want_q if k not in q})
        check("quantities carry what the table reads", not qmiss, qmiss)
        idents = {p["identity"] for p in R["pipes"]}
        keyed = {f"{q['base']}|DN{q['dn'] if q['dn'] is not None else '?'}" for q in R["quantities"]}
        check("run drill-down finds its runs", bool(idents & keyed), sorted(idents)[:2] + sorted(keyed)[:2])
        pid = R["pipes"][0]["physical_pipe_id"]
        w = c.get(f"/api/jobs/{j['id']}/why/{pid}", headers=H)
        check("why", w.status_code == 200 and bool(w.json().get("evidence_chain")), w.text[:200])

    arts = c.get(f"/api/jobs/{j['id']}/artifacts", headers=H)
    check("artifacts", arts.status_code == 200 and len(arts.json()) > 20, len(arts.json()) if arts.status_code == 200 else arts.text)
    for a in (arts.json() if arts.status_code == 200 else [])[:60]:
        rr = c.get(f"/api/jobs/{j['id']}/artifacts/{a['name']}", headers=H)
        if rr.status_code != 200:
            check(f"artifact {a['name']}", False, rr.status_code)
    for fmt in ("xlsx", "csv", "json", "report", "pdf"):
        rr = c.get(f"/api/jobs/{j['id']}/export/{fmt}", headers=H)
        check(f"export {fmt}", rr.status_code == 200, rr.status_code)

    # corrections round trip
    name = R["quantities"][0]["designation"]
    eng = R["quantities"][0]["confirmed_total_m"]
    cr = c.post(f"/api/drawings/{d['id']}/corrections", headers=H, json={
        "kind": "quantity", "designation": name, "job_id": j["id"], "payload": {"meters": eng + 3}, "note": "syscheck"})
    check("add correction", cr.status_code == 200, cr.text[:200])
    R2 = c.get(f"/api/jobs/{j['id']}/result", headers=H)
    check("result after correction 200", R2.status_code == 200, R2.text[:400])
    if R2.status_code == 200:
        R2 = R2.json()
        row = next(q for q in R2["quantities"] if q["designation"] == name)
        check("correction applied", abs(row["confirmed_total_m"] - (eng + 3)) < 1e-6, row["confirmed_total_m"])
        check("engine figure kept", abs(row["engine_total_m"] - eng) < 1e-6, row.get("engine_total_m"))
    check("undo correction", c.delete(f"/api/drawings/{d['id']}/corrections/{cr.json()['id']}", headers=H).status_code == 200)
    check("lessons", c.get("/api/lessons", headers=H).status_code == 200)

    # the static frontend the container serves
    # the container serves the built frontend from VVS_STATIC_DIR; without a build there is nothing to serve
    dist = os.path.join(ROOT, "frontend", "dist", "index.html")
    if os.path.exists(dist):
        check("index served", c.get("/").status_code == 200)
    else:
        print("  --   index served (ingen byggd frontend i den här körningen)")

print()
print("ALLA STEG OK" if not FAIL else f"{len(FAIL)} FEL: {FAIL}")
sys.exit(1 if FAIL else 0)
