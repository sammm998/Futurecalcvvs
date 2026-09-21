"""Huset lämnar systemet som IFC, GLB, SVG, DXF och PDF - och det som kommer tillbaka är samma hus.

Fyra saker prövas: att serverns kroppar är webbläsarens (samma hus byggt i TypeScript, varje prisma jämförd);
att varje export går att öppna (IFC parsas, GLB packas upp, PDF läses, SVG är XML, DXF har sina lager); att
importörerna läser tillbaka vad exporterna skrev (en IfcWall blir en vägg med samma tjocklek, en dörr sitter i
sin vägg); och att ett underlag utan skala är just utan skala - inte en gissning.
"""
import io
import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
FRONT = os.path.join(ROOT, "frontend")
ESBUILD = os.path.join(FRONT, "node_modules", ".bin", "esbuild")


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("cadx")
    os.environ["VVS_DATABASE_URL"] = f"sqlite:///{tmp}/test.db"
    os.environ["VVS_STORAGE_ROOT"] = str(tmp / "storage")
    os.environ["VVS_SECRET_KEY"] = "test"
    sys.path.insert(0, os.path.join(ROOT, "backend"))
    for m in list(sys.modules):
        if m.startswith("app"):
            del sys.modules[m]
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def house(tmp_path_factory):
    if not os.path.exists(ESBUILD):
        pytest.skip("frontend/node_modules saknas")
    out = str(tmp_path_factory.mktemp("house") / "house.fixture.js")
    b = subprocess.run([ESBUILD, "src/cad/house.fixture.ts", "--bundle", "--platform=node", "--format=cjs", f"--outfile={out}", "--log-level=warning"],
                       cwd=FRONT, capture_output=True, text=True, timeout=120)
    assert b.returncode == 0, b.stderr
    r = subprocess.run(["node", out], capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr[-800:]
    return json.loads(r.stdout.strip().splitlines()[-1])


@pytest.fixture(scope="module")
def sheet(client, house):
    r = client.post("/api/auth/register", json={"email": "ifc@example.com", "password": "hemligt1"}).json()
    H = {"Authorization": f"Bearer {r['access_token']}"}
    p = client.post("/api/projects", json={"name": "Kv Eken", "description": ""}, headers=H).json()
    s = client.post("/api/cad/sheets", json={"project_id": p["id"], "name": "Hus A", "paper": "A1", "scale_ratio": 100}, headers=H).json()
    doc = json.loads(json.dumps(house["doc"]))
    doc["sheets"] = [{"id": "sh1", "name": "A-40-1-01", "paper": "A1", "width_mm": 841, "height_mm": 594,
                      "title": {"number": "A-40-1-01", "name": "Plan 0", "project": "Kv Eken", "revision": "A", "date": "2026-09-12"},
                      "viewports": [{"id": "vp1", "view": doc["views"][0]["id"], "at": [20, 20], "size": [500, 400], "scale_ratio": 100}]}]
    assert client.put(f"/api/cad/sheets/{s['id']}", json={"content": doc}, headers=H).status_code == 200
    return H, s["id"], p["id"]


def test_the_server_has_the_same_solids_as_the_browser(client, house, sheet):
    H, sid, _ = sheet
    g = client.get(f"/api/cad/sheets/{sid}/geometry", headers=H).json()
    for e in house["doc"]["entities"]:
        ts, py = house["solids"][e["id"]], g["solids"][e["id"]]
        assert len(ts) == len(py), e["id"]
        for a, b in zip(ts, py):
            assert [[round(x, 3), round(y, 3)] for x, y in a["poly"]] == [[round(x, 3), round(y, 3)] for x, y in b["poly"]], e["id"]
            assert abs(a["z0"] - b["z0"]) < 1e-6 and abs(a["z1"] - b["z1"]) < 1e-6, e["id"]
            if a.get("top"):
                assert [round(v, 3) for v in a["top"]] == [round(v, 3) for v in b["top"]], e["id"]
    assert g["bounds"][0] == -2000 and g["bounds"][2] == 12000        # röret sticker ut två meter åt varje håll


def test_every_export_opens(client, sheet):
    H, sid, _ = sheet
    ifc = client.get(f"/api/cad/sheets/{sid}/export.ifc", headers=H)
    assert ifc.status_code == 200 and ifc.text.startswith("ISO-10303-21;") and "FILE_SCHEMA(('IFC4'))" in ifc.text
    body = ifc.text
    assert body.count("IFCWALL(") == 4 and body.count("IFCOPENINGELEMENT(") == 2 and "IFCDOOR(" in body and "IFCWINDOW(" in body
    assert body.count("IFCBUILDINGSTOREY(") == 3 and "IFCPIPESEGMENT(" in body and "IFCDUCTSEGMENT(" in body and "IFCSPACE(" in body
    assert "IFCRELVOIDSELEMENT(" in body and "IFCRELFILLSELEMENT(" in body and "IFCRELASSOCIATESMATERIAL(" in body
    # guid-erna är stabila för samma objekt och giltiga (första tecknet 0-3)
    again = client.get(f"/api/cad/sheets/{sid}/export.ifc", headers=H).text
    wall_lines = [l for l in body.splitlines() if "IFCWALL(" in l]
    assert wall_lines == [l for l in again.splitlines() if "IFCWALL(" in l]
    assert all(l.split("('")[1][0] in "0123" for l in wall_lines)

    glb = client.get(f"/api/cad/sheets/{sid}/export.glb", headers=H)
    assert glb.status_code == 200 and glb.content[:4] == b"glTF"
    from app.cad_export import read_glb
    j = read_glb(glb.content)
    names = {n["name"] for n in j["nodes"]}
    assert {"w_s", "w_e", "fl0", "c1", "b1", "r1", "p1", "k1", "d1", "f1"} <= names
    assert all(a["min"] and a["max"] for a in j["accessors"] if a["type"] == "VEC3")

    svg = client.get(f"/api/cad/sheets/{sid}/export.svg", headers=H)
    assert svg.status_code == 200
    root = ET.fromstring(svg.text)
    assert root.tag.endswith("svg") and svg.text.count("<polygon") >= 5 and "101 Kontor" in svg.text

    dxf = client.get(f"/api/cad/sheets/{sid}/export.dxf", headers=H)
    assert dxf.status_code == 200 and "LWPOLYLINE" in dxf.text and "$INSUNITS" in dxf.text and "Arkitektur" in dxf.text

    import pymupdf
    pdf = client.get(f"/api/cad/sheets/{sid}/export.pdf?paper=A1&ratio=100", headers=H)
    assert pdf.status_code == 200
    d = pymupdf.open(stream=pdf.content)
    text = d[0].get_text()
    assert "SKALA 1:100" in text and "Kv Eken" in text and "101 Kontor" in text
    assert abs(d[0].rect.width / 72 * 25.4 - 841) < 1

    blad = client.get(f"/api/cad/sheets/{sid}/sheets/sh1.pdf", headers=H)
    assert blad.status_code == 200
    text = pymupdf.open(stream=blad.content)[0].get_text()
    assert "A-40-1-01" in text and "REV A" in text and "Plan 0  1:100" in text

    # en fasad och ett snitt går också att exportera som vy
    view = {"id": "v_fasad", "kind": "elevation", "name": "Fasad S", "dir": "S", "scale_ratio": 100}
    sheet_doc = client.get(f"/api/cad/sheets/{sid}", headers=H).json()["content"]
    sheet_doc["views"].append(view)
    sheet_doc["views"].append({"id": "v_snitt", "kind": "section", "name": "Sektion A-A", "line": [[-1000, 7500], [11000, 7500]], "depth": 3000, "scale_ratio": 100})
    assert client.put(f"/api/cad/sheets/{sid}", json={"content": sheet_doc}, headers=H).status_code == 200
    fs = client.get(f"/api/cad/sheets/{sid}/export.svg?view=v_fasad", headers=H)
    assert fs.status_code == 200 and fs.text.count("<polygon") >= 4
    ss = client.get(f"/api/cad/sheets/{sid}/export.dxf?view=v_snitt", headers=H)
    assert ss.status_code == 200 and ss.text.count("LWPOLYLINE") >= 5
    assert client.get(f"/api/cad/sheets/{sid}/export.xyz", headers=H).status_code == 400


def test_what_was_exported_comes_back_as_the_same_house(client, sheet):
    H, sid, _ = sheet
    ifc = client.get(f"/api/cad/sheets/{sid}/export.ifc", headers=H).text
    r = client.post(f"/api/cad/sheets/{sid}/import", files={"file": ("hus.ifc", ifc.encode(), "application/x-step")}, headers=H)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["kind"] == "entities" and [l["elevation_mm"] for l in j["levels"]] == [0, 3200, 6400]
    walls = [e for e in j["entities"] if e["type"] == "wall"]
    assert len(walls) == 4 and all(abs(w["thickness"] - 300) < 1e-6 and abs(w["height"] - 3200) < 1e-6 for w in walls)
    assert all(e["provenance"] == "IMPORTED_IFC" for e in j["entities"])
    door = next(e for e in j["entities"] if e["type"] == "door")
    host = next(w for w in walls if w["id"] == door["host"])
    assert host["p"] == [[0, 0], [10000, 0]] and abs(door["t"] - 0.5) < 1e-6 and abs(door["width"] - 1000) < 1e-6 and abs(door["height"] - 2100) < 1e-6
    win = next(e for e in j["entities"] if e["type"] == "window")
    assert abs(win["sill"] - 900) < 1e-6 and abs(win["t"] - 0.2) < 1e-6
    col = next(e for e in j["entities"] if e["type"] == "column")
    assert col["profile"] == {"kind": "rect", "w": 300, "d": 300} and col["p"] == [[5000, 7500]]
    pipe = next(e for e in j["entities"] if e["type"] == "pipe")
    assert pipe["dn"] == 25 and pipe["path"] == [[-2000, 3000, 1000], [12000, 3000, 1000]]
    # det importerade är ett giltigt dokument
    doc = client.get(f"/api/cad/sheets/{sid}", headers=H).json()["content"]
    doc2 = dict(doc, levels=j["levels"], entities=j["entities"], layers=[{"id": l, "name": l, "color": "#111", "visible": True, "locked": False, "width": 0.35, "discipline": "ALLMAN"} for l in j["layers"]])
    assert client.post("/api/cad/validate", json={"content": doc2}, headers=H).json()["problems"] == []

    dxf = client.get(f"/api/cad/sheets/{sid}/export.dxf", headers=H).text
    r = client.post(f"/api/cad/sheets/{sid}/import", files={"file": ("hus.dxf", dxf.encode(), "application/dxf")}, headers=H).json()
    assert r["count"] >= 15 and {"polyline", "text"} <= {e["type"] for e in r["entities"]} and r["assumptions"] == []
    wall_ring = next(e for e in r["entities"] if e["type"] == "polyline" and e["closed"] and len(e["p"]) == 4)
    assert all(abs(p[1] - 150) < 1e-6 or abs(p[1] + 150) < 1e-6 for p in wall_ring["p"])   # sydväggens fotavtryck, y vänd tillbaka

    svg = client.get(f"/api/cad/sheets/{sid}/export.svg", headers=H).text
    r = client.post(f"/api/cad/sheets/{sid}/import", files={"file": ("hus.svg", svg.encode(), "image/svg+xml")}, headers=H).json()
    assert r["count"] >= 15 and "101 Kontor" in {e.get("text") for e in r["entities"]}

    assert client.post(f"/api/cad/sheets/{sid}/import", files={"file": ("x.dwg", b"AC1027", "application/octet-stream")}, headers=H).status_code == 400


def test_a_mesh_becomes_a_reference_with_its_box(client, sheet):
    H, sid, _ = sheet
    obj = "v 0 0 0\nv 2 0 0\nv 2 1 0\nv 0 1 3\nf 1 2 3\nf 1 3 4\n"
    r = client.post(f"/api/cad/sheets/{sid}/import", files={"file": ("stol.obj", obj.encode(), "text/plain")}, headers=H).json()
    assert r["kind"] == "mesh" and r["format"] == "obj" and r["bounds"]["min"] == [0, 0, 0] and r["bounds"]["max"] == [2, 1, 3]
    a = client.get(f"/api/cad/assets/{r['asset'].split('/assets/')[0].split('/')[-1]}/{r['asset'].rsplit('/', 1)[-1]}", headers=H)
    assert a.status_code == 200 and a.text == obj
    glb = client.get(f"/api/cad/sheets/{sid}/export.glb", headers=H).content
    r = client.post(f"/api/cad/sheets/{sid}/import", files={"file": ("hus.glb", glb, "model/gltf-binary")}, headers=H).json()
    assert r["kind"] == "mesh" and r["bounds"]["vertices"] > 0 and r["bounds"]["min"][0] <= -2.0


def test_an_underlay_without_a_scale_says_so(client, sheet):
    H, sid, _ = sheet
    import pymupdf
    pdf = pymupdf.open()
    pg = pdf.new_page(width=595, height=842)
    pg.draw_rect(pymupdf.Rect(100, 100, 400, 500))
    data = pdf.tobytes()
    r = client.post(f"/api/cad/sheets/{sid}/underlay", files={"file": ("plan.pdf", data, "application/pdf")}, data={"page": "0"}, headers=H)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["scale_state"] == "UNCALIBRATED" and j["mm_per_px"] is None and j["px"][1] > j["px"][0] and j["source"]["px_per_pt"] > 1
    png = client.get(f"/api/cad/assets/{sid}/{j['asset'].rsplit('/', 1)[-1]}", headers=H)
    assert png.status_code == 200 and png.content[:8] == b"\x89PNG\r\n\x1a\n"
    assert client.post(f"/api/cad/sheets/{sid}/underlay", files={"file": ("plan.pdf", data, "application/pdf")}, data={"page": "3"}, headers=H).status_code == 400
    # ett underlag i dokumentet med skala noll avvisas; utan skala godtas det som okalibrerat
    doc = client.get(f"/api/cad/sheets/{sid}", headers=H).json()["content"]
    u = {"id": "u1", "type": "underlay", "layer": doc["layers"][0]["id"], "discipline": "ALLMAN", "phase": "NEW", "provenance": "DETECTED_FROM_PDF", "version": 1,
         "level": doc["levels"][0]["id"], "p": [[0, 0]], "asset": j["asset"], "px": j["px"], "mm_per_px": None, "scale_state": "UNCALIBRATED"}
    ok = dict(doc, entities=doc["entities"] + [u])
    assert client.post("/api/cad/validate", json={"content": ok}, headers=H).json()["problems"] == []
    bad = dict(doc, entities=doc["entities"] + [dict(u, mm_per_px=0)])
    assert any(p.get("field") == "mm_per_px" for p in client.post("/api/cad/validate", json={"content": bad}, headers=H).json()["problems"])
    # en bild fungerar också
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 40, 30), False)
    pix.clear_with(200)
    r = client.post(f"/api/cad/sheets/{sid}/underlay", files={"file": ("foto.png", pix.tobytes("png"), "image/png")}, headers=H).json()
    assert r["px"] == [40, 30] and r["scale_state"] == "UNCALIBRATED"
    # någon annans blad ger inte ut sina filer
    other = client.post("/api/auth/register", json={"email": "annan@example.com", "password": "hemligt1"}).json()
    H2 = {"Authorization": f"Bearer {other['access_token']}"}
    assert client.get(f"/api/cad/assets/{sid}/{j['asset'].rsplit('/', 1)[-1]}", headers=H2).status_code == 404
