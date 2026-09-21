"""Ett helt hus, från första väggen till IFC - 29 steg genom API:t, kärnan och exporterna.

Huset är ett tvåplanshus med källare: nivåer och rutnät; ytterväggar, innerväggar, dörrar, fönster; bjälklag,
sadeltak, undertak; trappa och räcke; pelare, balkar, grund; rum; rör (KV, VV, S), kanaler, kabelstege, en
pump med anslutningar och apparater; text, mått och hänvisningar. Sedan: validering, mängder som stämmer med
handräkning, materialmängder, kollisioner med hålförslag som godkänns, snitt och fasad, ett ritningsblad,
revisioner som återställs, agentens förslag, och varje export - IFC, GLB, DXF, SVG, PDF - som öppnas och
läses tillbaka. Kollisionerna och snitten räknas av samma kod som ritbordet kör (cli.ts genom node).

Varje steg är en funktion; ordningen är husets. Faller ett steg står det vilket.
"""
import json
import os
import subprocess
import sys

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
FRONT = os.path.join(ROOT, "frontend")
ESBUILD = os.path.join(FRONT, "node_modules", ".bin", "esbuild")


def needs_the_core():
    """Steg som bara går att ta när ritbordets kärna går att köra.

    Huset byggs i ordning och varje steg står på det föregående. Fem av stegen - validering, mängder,
    kollisioner, hålen som godtas, snittet - körs av samma kod som ritbordet, genom node, och hoppas över där
    node_modules saknas. De två sista stegen läser huset de stegen byggde: revisionen som hålet skapade och
    hålet självt i IFC-filen.

    Utan den här spärren hoppade de fem över och de två föll - vilket är precis vad som hände i bygget, där
    node_modules inte installeras för motorns prov. Ett prov som faller för att ett annat hoppades över säger
    ingenting om koden, och det stod rött i tvåhundra byggen innan någon läste vad det stod.
    """
    if not os.path.exists(ESBUILD):
        pytest.skip("frontend/node_modules saknas: huset är inte färdigbyggt utan stegen som kör kärnan")


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("house29")
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
def core(tmp_path_factory):
    """Kärnan som kommando: samma kod som ritbordet, körd med node."""
    if not os.path.exists(ESBUILD):
        pytest.skip("frontend/node_modules saknas")
    out = str(tmp_path_factory.mktemp("cli") / "cli.js")
    b = subprocess.run([ESBUILD, "src/cad/cli.ts", "--bundle", "--platform=node", "--format=cjs", f"--outfile={out}", "--log-level=warning"],
                       cwd=FRONT, capture_output=True, text=True, timeout=120)
    assert b.returncode == 0, b.stderr

    def run(doc: dict, section=None, elevation="S") -> dict:
        r = subprocess.run(["node", out], input=json.dumps({"doc": doc, "section": section, "elevation": elevation}), capture_output=True, text=True, timeout=120)
        assert r.returncode == 0, r.stderr[-800:]
        return json.loads(r.stdout)
    return run


class House:
    """Huset som byggs steg för steg; varje steg sparar en revision genom API:t."""

    def __init__(self, client):
        self.c = client
        r = client.post("/api/auth/register", json={"email": "hus29@example.com", "password": "hemligt1"}).json()
        self.H = {"Authorization": f"Bearer {r['access_token']}"}
        self.pid = client.post("/api/projects", json={"name": "Kv Björken", "description": ""}, headers=self.H).json()["id"]
        self.sid = client.post("/api/cad/sheets", json={"project_id": self.pid, "name": "Hus 1", "paper": "A1", "scale_ratio": 100}, headers=self.H).json()["id"]
        self.doc = {"version": 2, "units": "mm", "project": {"name": "Kv Björken"}, "building": {"name": "Hus 1"}, "site": {},
                    "levels": [], "grids": [], "layers": [
                        {"id": "l_ark", "name": "Arkitektur", "color": "#222", "visible": True, "locked": False, "width": 0.35, "discipline": "ARK"},
                        {"id": "l_k", "name": "Konstruktion", "color": "#7048e8", "visible": True, "locked": False, "width": 0.35, "discipline": "KONSTR"},
                        {"id": "l_vvs", "name": "VVS", "color": "#1f6feb", "visible": True, "locked": False, "width": 0.35, "discipline": "VVS"},
                        {"id": "l_vent", "name": "Ventilation", "color": "#0b7285", "visible": True, "locked": False, "width": 0.35, "discipline": "VENT"},
                        {"id": "l_el", "name": "El", "color": "#b58900", "visible": True, "locked": False, "width": 0.35, "discipline": "EL"}],
                    "materials": [{"id": "m_concrete", "name": "Betong C30/37", "category": "betong", "density_kg_m3": 2400},
                                  {"id": "m_steel", "name": "Stål S355", "category": "stål", "density_kg_m3": 7850},
                                  {"id": "m_wood", "name": "Trä", "category": "trä", "density_kg_m3": 500},
                                  {"id": "m_gypsum", "name": "Gips på regel", "category": "skivor", "density_kg_m3": None},
                                  {"id": "m_copper", "name": "Koppar", "category": "rör", "density_kg_m3": 8960}],
                    "blocks": [], "entities": [], "views": [], "sheets": [], "constraints": [], "settings": {}, "revision": 0}
        self.revisions = []

    def save(self, label: str) -> dict:
        r = self.c.put(f"/api/cad/sheets/{self.sid}", json={"content": self.doc, "label": label, "base_revision": self.doc.get("revision", 0)}, headers=self.H)
        assert r.status_code == 200, (label, r.text)
        self.doc = r.json()["content"]
        self.revisions.append((self.doc["revision"], label))
        return self.doc

    def add(self, *ents):
        for e in ents:
            e.setdefault("phase", "NEW"); e.setdefault("provenance", "USER_MODELLED"); e.setdefault("version", 1)
            self.doc["entities"].append(e)

    def E(self, eid):
        return next(e for e in self.doc["entities"] if e["id"] == eid)


def _ark(eid, **f):
    return dict(id=eid, layer="l_ark", discipline="ARK", **f)


def _k(eid, **f):
    return dict(id=eid, layer="l_k", discipline="KONSTR", **f)


@pytest.fixture(scope="module")
def house(client):
    return House(client)


# ---------------------------------------------------------------- 1-4: projekt, nivåer, rutnät, vyer

def test_01_the_project_and_the_sheet_exist(house):
    assert house.sid and house.pid


def test_02_levels_are_what_the_user_says(house):
    house.doc["levels"] = [{"id": "lv_k", "name": "Källare", "elevation_mm": -2700}, {"id": "lv_0", "name": "Plan 0", "elevation_mm": 0},
                           {"id": "lv_1", "name": "Plan 1", "elevation_mm": 2900}, {"id": "lv_tak", "name": "Tak", "elevation_mm": 5800}]
    house.doc["views"] = [{"id": f"v_{l['id']}", "kind": "plan", "name": l["name"], "level": l["id"], "scale_ratio": 100} for l in house.doc["levels"]] + [{"id": "v_3d", "kind": "3d", "name": "3D"}]
    house.doc["settings"] = {"active_level": "lv_0", "active_view": "v_lv_0"}
    d = house.save("Nivåer")
    assert [l["elevation_mm"] for l in d["levels"]] == [-2700, 0, 2900, 5800] and d["revision"] == 1


def test_03_the_grid(house):
    house.doc["grids"] = [{"id": f"g_{c}", "label": c, "p": [[x, -1000], [x, 11000]]} for c, x in zip("ABCD", (0, 4000, 8000, 12000))] + \
                         [{"id": f"g_{n}", "label": str(n), "p": [[-1000, y], [13000, y]]} for n, y in zip((1, 2, 3), (0, 5000, 10000))]
    assert len(house.save("Rutnät")["grids"]) == 7


def test_04_every_level_has_a_plan_view(house):
    assert {v["level"] for v in house.doc["views"] if v["kind"] == "plan"} == {l["id"] for l in house.doc["levels"]}


# ---------------------------------------------------------------- 5-8: väggar, dörrar, fönster

def _wall(eid, a, b, level, thickness=300, top=None, **f):
    w = _ark(eid, type="wall", p=[a, b], thickness=thickness, base_level=level, alignment="centre", material="m_concrete" if thickness >= 200 else "m_gypsum", **f)
    if top:
        w["top_level"] = top
    return w


def test_05_exterior_walls_on_two_floors_and_a_basement(house):
    ring = [[0, 0], [12000, 0], [12000, 10000], [0, 10000]]
    for lv, top in (("lv_k", "lv_0"), ("lv_0", "lv_1"), ("lv_1", "lv_tak")):
        for i in range(4):
            house.add(_wall(f"w_{lv}_{i}", ring[i], ring[(i + 1) % 4], lv, 300 if lv != "lv_k" else 250, top))
    d = house.save("Ytterväggar")
    assert len([e for e in d["entities"] if e["type"] == "wall"]) == 12


def test_06_interior_walls(house):
    house.add(_wall("wi_0_a", [6000, 0], [6000, 10000], "lv_0", 120, "lv_1"), _wall("wi_0_b", [6000, 5000], [12000, 5000], "lv_0", 120, "lv_1"),
              _wall("wi_1_a", [6000, 0], [6000, 10000], "lv_1", 120, "lv_tak"))
    assert len([e for e in house.save("Innerväggar")["entities"] if e["type"] == "wall"]) == 15


def test_07_doors_sit_in_walls_and_follow_them(house):
    house.add(_ark("d_entre", type="door", host="w_lv_0_0", t=0.25, width=1000, height=2100, swing="left", name="Entré"),
              _ark("d_in1", type="door", host="wi_0_a", t=0.3, width=900, height=2100, swing="right"),
              _ark("d_in2", type="door", host="wi_0_b", t=0.5, width=800, height=2100, swing="left"),
              _ark("d_1", type="door", host="wi_1_a", t=0.7, width=900, height=2100, swing="left"))
    d = house.save("Dörrar")
    # flyttas väggen följer dörren: läget är en andel längs väggen, inte en koordinat
    w = house.E("w_lv_0_0")
    w["p"] = [[0, -500], [12000, -500]]
    d = house.save("Sydväggen flyttad 500 mm")
    door = house.E("d_entre")
    assert door["t"] == 0.25 and house.E("w_lv_0_0")["p"][0][1] == -500
    assert any(r["revision"] == d["revision"] for r in house.c.get(f"/api/cad/sheets/{house.sid}/revisions", headers=house.H).json()["rows"])


def test_08_windows(house):
    for i, host in enumerate(("w_lv_0_0", "w_lv_0_1", "w_lv_0_2", "w_lv_0_3", "w_lv_1_0", "w_lv_1_1", "w_lv_1_2", "w_lv_1_3")):
        house.add(_ark(f"f_{i}", type="window", host=host, t=0.6, width=1200, height=1300, sill=800))
    assert len([e for e in house.save("Fönster")["entities"] if e["type"] == "window"]) == 8


# ---------------------------------------------------------------- 9-12: bjälklag, tak, undertak, trappa och räcke

def test_09_floors_on_every_level(house):
    ring = [[0, 0], [12000, 0], [12000, 10000], [0, 10000]]
    for lv, th in (("lv_k", 200), ("lv_0", 250), ("lv_1", 250)):
        house.add(_ark(f"fl_{lv}", type="floor", p=ring, thickness=th, level=lv, material="m_concrete", structural=True,
                       holes=[[[8000, 6000], [9500, 6000], [9500, 9000], [8000, 9000]]] if lv == "lv_1" else None))
    assert len([e for e in house.save("Bjälklag")["entities"] if e["type"] == "floor"]) == 3


def test_10_a_pitched_roof_with_its_ridge(house):
    house.add(_ark("roof", type="roof", p=[[-500, -500], [12500, -500], [12500, 10500], [-500, 10500]], kind="pitched", slope_deg=30, ridge=[[6000, -500], [6000, 10500]], thickness=300, level="lv_tak", material="m_wood"))
    assert house.save("Tak")["entities"][-1]["kind"] == "pitched"


def test_11_a_ceiling(house):
    house.add(_ark("ceil_0", type="ceiling", p=[[0, 0], [6000, 0], [6000, 10000], [0, 10000]], height_offset=2500, thickness=30, level="lv_0"))
    assert house.save("Undertak")["entities"][-1]["type"] == "ceiling"


def test_12_a_stair_and_a_railing(house):
    house.add(_ark("stair", type="stair", kind="straight", p=[[8000, 9000], [8000, 6000]], base_level="lv_0", top_level="lv_1", width=1000, risers=16, tread_d=270),
              _ark("rail", type="railing", p=[[8500, 9000], [8500, 6000]], height=1100, level="lv_1"))
    d = house.save("Trappa och räcke")
    assert {e["type"] for e in d["entities"]} >= {"stair", "railing"}


# ---------------------------------------------------------------- 13-15: stomme

def test_13_columns_on_the_grid(house):
    for c, x in zip("BC", (4000, 8000)):
        for n, y in zip((2,), (5000,)):
            for lv in ("lv_k", "lv_0"):
                house.add(_k(f"col_{c}{n}_{lv}", type="column", p=[[x, y]], profile={"kind": "rect", "w": 300, "d": 300}, base_level=lv, material="m_concrete", grid=[f"g_{c}", f"g_{n}"]))
    assert len([e for e in house.save("Pelare")["entities"] if e["type"] == "column"]) == 4


def test_14_beams_supported_by_columns(house):
    house.add(_k("beam_0", type="beam", p=[[0, 5000], [12000, 5000]], profile={"kind": "I", "w": 200, "d": 400, "t": 12, "name": "HEA 400"}, level="lv_0", material="m_steel", supports=["col_B2_lv_k", "col_C2_lv_k"]),
              _k("beam_1", type="beam", p=[[0, 5000], [12000, 5000]], profile={"kind": "rect", "w": 300, "d": 500}, level="lv_1", material="m_concrete", supports=["col_B2_lv_0", "col_C2_lv_0"]))
    assert len([e for e in house.save("Balkar")["entities"] if e["type"] == "beam"]) == 2


def test_15_foundations(house):
    house.add(_k("fnd_slab", type="foundation", kind="slab", p=[[0, 0], [12000, 0], [12000, 10000], [0, 10000]], h=300, level="lv_k", material="m_concrete"),
              _k("fnd_strip", type="foundation", kind="strip", p=[[0, 0], [12000, 0], [12000, 10000], [0, 10000], [0, 0]], w=600, h=400, level="lv_k", offset=-300, material="m_concrete"),
              _k("fnd_B2", type="foundation", kind="isolated", p=[[4000, 5000]], w=1200, d=1200, h=400, level="lv_k", offset=-300, material="m_concrete"))
    assert len([e for e in house.save("Grund")["entities"] if e["type"] == "foundation"]) == 3


# ---------------------------------------------------------------- 16: rum

def test_16_rooms_with_numbers(house):
    house.add(_ark("rm_101", type="room", p=[[150, 150], [5940, 150], [5940, 9850], [150, 9850]], level="lv_0", name="Vardagsrum", number="101"),
              _ark("rm_102", type="room", p=[[6060, 150], [11850, 150], [11850, 4940], [6060, 4940]], level="lv_0", name="Kök", number="102"),
              _ark("rm_103", type="room", p=[[6060, 5060], [11850, 5060], [11850, 9850], [6060, 9850]], level="lv_0", name="Hall", number="103"))
    assert len([e for e in house.save("Rum")["entities"] if e["type"] == "room"]) == 3


# ---------------------------------------------------------------- 17-21: installationer

def test_17_pipes_of_three_systems(house):
    V = lambda eid, **f: dict(id=eid, layer="l_vvs", discipline="VVS", **f)  # noqa: E731
    house.add(V("p_kv", type="pipe", path=[[-1500, 7000, 0], [11000, 7000, 0]], system="KV", dn=28, level="lv_0", elevation=2600, material="m_copper", designation="KV1"),
              V("p_vv", type="pipe", path=[[-1500, 7200, 0], [11000, 7200, 0]], system="VV", dn=22, level="lv_0", elevation=2600, material="m_copper", designation="VV1"),
              V("p_s", type="pipe", path=[[11000, 9000, 0], [11000, 500, 0], [-1500, 500, 0]], system="S", dn=110, level="lv_k", elevation=2300, designation="S1"),
              V("p_kv_upp", type="pipe", path=[[11000, 7000, 0], [11000, 7000, 3000]], system="KV", dn=22, level="lv_0", elevation=2600, material="m_copper", designation="KV1"))
    assert len([e for e in house.save("Rör")["entities"] if e["type"] == "pipe"]) == 4


def test_18_ducts(house):
    house.add(dict(id="k_tl", layer="l_vent", discipline="VENT", type="duct", path=[[-1500, 8500, 0], [11500, 8500, 0]], system="TL", shape="rect", w=400, h=200, level="lv_1", elevation=2500),
              dict(id="k_fl", layer="l_vent", discipline="VENT", type="duct", path=[[-1500, 9000, 0], [11500, 9000, 0]], system="FL", shape="round", d=250, level="lv_1", elevation=2500))
    assert len([e for e in house.save("Kanaler")["entities"] if e["type"] == "duct"]) == 2


def test_19_cable_trays_and_conduits(house):
    house.add(dict(id="ct_1", layer="l_el", discipline="EL", type="cable_tray", path=[[-1500, 300, 0], [11500, 300, 0]], system="EL", w=300, h=60, level="lv_k", elevation=2400),
              dict(id="cd_1", layer="l_el", discipline="EL", type="conduit", path=[[2000, 300, 0], [2000, 4000, 0]], system="EL", d=25, level="lv_k", elevation=2400))
    d = house.save("Kabelstege och elrör")
    assert {e["type"] for e in d["entities"]} >= {"cable_tray", "conduit"}


def test_20_a_pump_the_pipes_connect_to(house):
    house.add(dict(id="pump", layer="l_vvs", discipline="VVS", type="equipment", kind="pump", name="P1", p=[[11000, 7000, 2600]], size=[600, 400, 500], system="KV", level="lv_0",
                   connectors=[{"id": "c_in", "name": "IN", "kind": "in", "at": [0, 0, 0]}, {"id": "c_ut", "name": "UT", "kind": "out", "at": [0, 0, 0]}]))
    d = house.save("Pump")
    assert d["entities"][-1]["connectors"][0]["name"] == "IN"


def test_21_devices(house):
    house.add(dict(id="dev_1", layer="l_el", discipline="EL", type="device", kind="light", p=[[3000, 5000, 2500]], level="lv_0", system="EL"),
              dict(id="dev_2", layer="l_vent", discipline="VENT", type="device", kind="air_terminal", p=[[9000, 2500, 2500]], level="lv_1", system="TL"))
    assert len([e for e in house.save("Apparater")["entities"] if e["type"] == "device"]) == 2


# ---------------------------------------------------------------- 22-24: annotering, validering, mängder

def test_22_text_dimensions_and_leaders(house):
    house.add(_ark("t_1", type="text", p=[[500, 11500]], text="PLAN 0", h=5, level="lv_0"),
              _ark("t_rum", type="text", p=[[3000, 5000]], text="", h=2.5, level="lv_0", ref={"id": "rm_101", "field": "area"}),
              _ark("dim_1", type="dim", kind="aligned", p=[[0, -500], [12000, -500]], off=-800, level="lv_0", refs=[{"id": "w_lv_0_0", "grip": 0}, {"id": "w_lv_0_0", "grip": 1}]),
              _ark("ld_1", type="leader", p=[[11000, 7000], [10000, 8500]], text="P1 pump", level="lv_0"))
    d = house.save("Annotering")
    assert {e["type"] for e in d["entities"]} >= {"text", "dim", "leader"}


def test_23_the_whole_house_validates(house, core):
    assert house.c.post("/api/cad/validate", json={"content": house.doc}, headers=house.H).json()["problems"] == []
    out = core(house.doc)
    assert out["problems"] == []
    rel = out["relations"]
    assert {"kind": "HOSTED_BY", "from": "d_entre", "to": "w_lv_0_0"} in rel
    assert {"kind": "SUPPORTED_BY", "from": "beam_0", "to": "col_B2_lv_k"} in rel
    assert {"kind": "ATTACHED_TO_GRID", "from": "col_B2_lv_0", "to": "g_B/g_2"} in rel
    conns = [r for r in rel if r["kind"] == "CONNECTS_TO"]
    assert {"kind": "CONNECTS_TO", "from": "p_kv", "to": "pump"} in conns and {"kind": "CONNECTS_TO", "from": "p_kv_upp", "to": "pump"} in conns


def test_24_quantities_match_hand_counting(house, core):
    q = house.c.get(f"/api/cad/sheets/{house.sid}/quantities", headers=house.H).json()
    rows = {r["id"]: r for r in q["rows"]}
    # sydväggen plan 0: 12 m × 2,9 m − entrédörr 1×2,1 − fönster 1,2×1,3 = 34,8 − 2,1 − 1,56 = 31,14 m²
    assert abs(rows["w_lv_0_0"]["area_m2"] - 31.14) < 1e-6 and abs(rows["w_lv_0_0"]["length_m"] - 12) < 1e-6
    assert abs(rows["w_lv_0_0"]["volume_m3"] - 31.14 * 0.3) < 1e-6 and abs(rows["w_lv_0_0"]["mass_kg"] - 31.14 * 0.3 * 2400) < 1e-3
    # bjälklaget plan 1: 120 m² minus hålet 1,5 × 3 = 4,5 m² ⇒ 115,5 m² och 28,875 m³
    assert abs(rows["fl_lv_1"]["area_m2"] - 115.5) < 1e-6 and abs(rows["fl_lv_1"]["volume_m3"] - 28.875) < 1e-6
    # rummen: 5,79 × 9,7 = 56,163 m²
    assert abs(rows["rm_101"]["area_m2"] - 56.163) < 1e-6
    # rören: KV 12,5 m vågrätt + 3 m lodrätt; spillvatten 8,5 + 12,5 = 21 m
    assert abs(rows["p_kv"]["length_m"] - 12.5) < 1e-6 and abs(rows["p_kv_upp"]["length_m"] - 3) < 1e-6 and abs(rows["p_s"]["length_m"] - 21) < 1e-6
    # gips utan densitet: ingen vikt, aldrig en gissad
    assert rows["wi_0_a"]["mass_kg"] is None and rows["wi_0_a"]["area_m2"] > 0
    # dörrar och fönster i stycken; pelare i volym; balken i stål
    groups = {g["key"]: g for g in q["groups"]}
    assert sum(g["count"] for k, g in groups.items() if k.startswith("door")) == 4 and sum(g["count"] for k, g in groups.items() if k.startswith("window")) == 8
    assert abs(rows["col_B2_lv_0"]["volume_m3"] - 0.3 * 0.3 * 2.9) < 1e-6
    hea = rows["beam_0"]
    assert hea["mass_kg"] is not None and abs(hea["mass_kg"] - (2 * 200 * 12 + (400 - 24) * 12) / 1e6 * 12 * 7850) < 1e-3
    # webbläsarens kärna räknar samma tal, grupp för grupp
    b = {g["key"]: g for g in core(house.doc)["quantities"]["groups"]}
    assert set(b) == set(groups)
    for k, g in groups.items():
        for f in ("count", "length_m", "area_m2", "volume_m3"):
            assert abs(float(b[k][f]) - float(g[f])) < 1e-6, (k, f)
    mats = {m["material"]["id"]: m for m in q["materials"]}
    assert mats["m_copper"]["mass_kg"] is not None and mats["m_gypsum"]["mass_kg"] is None and mats["m_concrete"]["volume_m3"] > 50


# ---------------------------------------------------------------- 25-26: kollisioner och hål som godkänns

def test_25_clashes_where_pipes_cross_walls(house, core):
    out = core(house.doc)
    pairs = {(c["a"], c["b"]) for c in out["clashes"]} | {(c["b"], c["a"]) for c in out["clashes"]}
    assert ("p_kv", "wi_0_a") in pairs and ("p_kv", "w_lv_0_3") in pairs, sorted(pairs)
    assert ("k_tl", "wi_1_a") in pairs
    # pelaren under balken är ingen kollision, och dörren i sin vägg är ingen
    assert ("beam_0", "col_B2_lv_k") not in pairs and ("d_entre", "w_lv_0_0") not in pairs
    high = [c for c in out["clashes"] if c["severity"] == "hög"]
    assert high and all(c["a_discipline"] != c["b_discipline"] for c in high)
    house.clashes, house.proposals = out["clashes"], out["proposals"]
    assert any(p["host"] == "wi_0_a" and p["through"] == "p_kv" for p in out["proposals"])


def test_26_approved_openings_remove_the_clash(house, core):
    p = next(p for p in house.proposals if p["host"] == "wi_0_a" and p["through"] == "p_kv")
    host = house.E("wi_0_a")
    a, b = host["p"]
    L = ((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2) ** 0.5
    t = ((p["at"][0] - a[0]) * (b[0] - a[0]) + (p["at"][1] - a[1]) * (b[1] - a[1])) / (L * L)
    house.add(_k("op_kv", type="opening", host="wi_0_a", t=t, width=p["size_mm"], height=p["size_mm"], sill=p["at"][2] - 0 - p["size_mm"] / 2, host_kind="wall", provenance="AGENT_CREATED_APPROVED"))
    house.save("Godkänt hål för KV1 genom innervägg")
    out = core(house.doc)
    pairs = {(c["a"], c["b"]) for c in out["clashes"]} | {(c["b"], c["a"]) for c in out["clashes"]}
    assert ("p_kv", "wi_0_a") not in pairs and ("p_kv", "w_lv_0_3") in pairs
    assert house.E("op_kv")["provenance"] == "AGENT_CREATED_APPROVED"


# ---------------------------------------------------------------- 27: snitt, fasad, blad

def test_27_section_elevation_and_a_drawing_sheet(house, core, client):
    out = core(house.doc, section=[[-1000, 6500], [13000, 6500]], elevation="S")   # tvärs huset, tvärs spillvattenröret
    ids = {s["id"] for s in out["section"]}
    assert {"w_lv_0_3", "w_lv_0_1", "fl_lv_0", "roof", "p_s"} <= ids
    roof = [s for s in out["section"] if s["id"] == "roof"][0]
    assert max(z for _, z in roof["poly"]) > 5800
    front = {s["id"] for s in out["elevation"]}
    assert {"w_lv_0_0", "d_entre", "f_0", "roof"} <= front
    house.doc["views"] += [{"id": "v_sec", "kind": "section", "name": "Sektion A-A", "line": [[-1000, 6500], [13000, 6500]], "depth": 4000, "scale_ratio": 50},
                           {"id": "v_fas", "kind": "elevation", "name": "Fasad mot söder", "dir": "S", "scale_ratio": 100}]
    house.doc["sheets"] = [{"id": "sh_1", "name": "Plan 0 och sektion", "paper": "A1", "width_mm": 841, "height_mm": 594,
                            "title": {"number": "A-40-1-001", "name": "Plan 0, sektion A-A", "project": "Kv Björken", "revision": "B", "date": "2026-09-13", "drawn_by": "AB", "scale": "1:100 / 1:50"},
                            "viewports": [{"id": "vp1", "view": "v_lv_0", "at": [15, 15], "size": [420, 400], "scale_ratio": 100, "title": "Plan 0"},
                                          {"id": "vp2", "view": "v_sec", "at": [450, 15], "size": [370, 250], "scale_ratio": 50, "title": "Sektion A-A"},
                                          {"id": "vp3", "view": "v_fas", "at": [450, 280], "size": [370, 200], "scale_ratio": 100, "title": "Fasad mot söder"}]}]
    house.save("Vyer och blad")
    import pymupdf
    pdf = client.get(f"/api/cad/sheets/{house.sid}/sheets/sh_1.pdf", headers=house.H)
    assert pdf.status_code == 200
    text = pymupdf.open(stream=pdf.content)[0].get_text()
    assert "A-40-1-001" in text and "Sektion A-A  1:50" in text and "Fasad mot söder  1:100" in text and "101 Vardagsrum" in text and "REV B" in text
    for view in ("v_sec", "v_fas", "v_lv_1"):
        r = client.get(f"/api/cad/sheets/{house.sid}/export.svg?view={view}", headers=house.H)
        assert r.status_code == 200 and r.text.count("<polygon") >= 3, view


# ---------------------------------------------------------------- 28: revisioner och agenten

def test_28_history_restores_and_the_agent_proposes(house, client):
    needs_the_core()
    revs = client.get(f"/api/cad/sheets/{house.sid}/revisions", headers=house.H).json()
    assert revs["current"] == house.doc["revision"] and len(revs["rows"]) == house.doc["revision"]
    labels = [r["label"] for r in revs["rows"]]
    assert "Sydväggen flyttad 500 mm" in labels and "Godkänt hål för KV1 genom innervägg" in labels
    before_move = next(r for r in revs["rows"] if r["label"] == "Dörrar")["revision"]
    r = client.post(f"/api/cad/sheets/{house.sid}/revisions/{before_move}/restore", headers=house.H).json()["content"]
    assert next(e for e in r["entities"] if e["id"] == "w_lv_0_0")["p"][0][1] == 0 and "pump" not in {e["id"] for e in r["entities"]}
    # ...och tillbaka till det senaste, så att resten av huset står kvar
    latest = client.post(f"/api/cad/sheets/{house.sid}/revisions/{house.doc['revision']}/restore", headers=house.H).json()["content"]
    assert "pump" in {e["id"] for e in latest["entities"]}
    house.doc = latest
    # en samtidig sparning från en gammal revision krockar
    assert client.put(f"/api/cad/sheets/{house.sid}", json={"content": house.doc, "base_revision": 1}, headers=house.H).status_code == 409
    # agenten föreslår ett rum i det tomma hörnet, med måtten användaren gav - och bladet är orört tills det godkänns
    n = len(house.doc["entities"])
    r = client.post(f"/api/cad/sheets/{house.sid}/agent/tool", json={"name": "skapa_rum", "arguments": {"kontur": [[6060, 5060], [11850, 5060], [11850, 9850], [6060, 9850]], "niva": "lv_1", "namn": "Sovrum", "nummer": "201"}}, headers=house.H).json()
    assert len(r["forslag"]) == 1 and r["forslag"][0]["item"]["provenance"] == "AGENT_CREATED_APPROVED"
    assert len(client.get(f"/api/cad/sheets/{house.sid}", headers=house.H).json()["content"]["entities"]) == n
    r = client.post(f"/api/cad/sheets/{house.sid}/agent/tool", json={"name": "skapa_dorr", "arguments": {"vagg_id": "wi_1_a", "lage_mm": 2000, "bredd_mm": 900}}, headers=house.H).json()
    assert r["forslag"] == [] and r["verktyg"][0]["resultat"].get("fraga_anvandaren") is True


# ---------------------------------------------------------------- 29: exporterna

def test_29_every_export_opens_and_ifc_comes_back_as_the_same_house(house, client):
    needs_the_core()
    H, sid = house.H, house.sid
    ifc = client.get(f"/api/cad/sheets/{sid}/export.ifc", headers=H).text
    assert ifc.count("IFCBUILDINGSTOREY(") == 4 and ifc.count("IFCWALL(") == 15 and ifc.count("IFCDOOR(") == 4 and ifc.count("IFCWINDOW(") == 8
    assert ifc.count("IFCOPENINGELEMENT(") == 13 and "IFCSTAIR(" in ifc and "IFCROOF(" in ifc and ifc.count("IFCFOOTING(") == 3 and ifc.count("IFCSPACE(") == 3
    assert "IFCPIPESEGMENT(" in ifc and "IFCDUCTSEGMENT(" in ifc and "IFCCABLECARRIERSEGMENT(" in ifc and "IFCBUILDINGELEMENTPROXY(" in ifc
    assert "IFCRELASSOCIATESMATERIAL(" in ifc and "'Pset_VVS'" in ifc
    r = client.post(f"/api/cad/sheets/{sid}/import", files={"file": ("hus.ifc", ifc.encode(), "application/x-step")}, headers=H).json()
    back = {e["type"]: 0 for e in r["entities"]}
    for e in r["entities"]:
        back[e["type"]] += 1
    assert back["wall"] == 15 and back["door"] == 4 and back["window"] == 8 and back["floor"] == 3 and back["column"] == 4 and back["beam"] == 2 and back["room"] == 3
    assert [l["elevation_mm"] for l in r["levels"]] == [-2700, 0, 2900, 5800]
    wall = next(e for e in r["entities"] if e["type"] == "wall" and abs(e["thickness"] - 120) < 1e-6)
    assert abs(wall["height"] - 2900) < 1e-6
    from app.cad_export import read_glb
    glb = client.get(f"/api/cad/sheets/{sid}/export.glb", headers=H).content
    j = read_glb(glb)
    assert len(j["nodes"]) >= 50 and {"roof", "stair", "p_s", "k_fl", "pump"} <= {n["name"] for n in j["nodes"]}
    dxf = client.get(f"/api/cad/sheets/{sid}/export.dxf?view=v_lv_0", headers=H).text
    assert "LWPOLYLINE" in dxf and "Rutnät" in dxf
    r = client.post(f"/api/cad/sheets/{sid}/import", files={"file": ("plan0.dxf", dxf.encode(), "application/dxf")}, headers=H).json()
    assert r["count"] > 30 and r["assumptions"] == []
    import pymupdf
    pdf = client.get(f"/api/cad/sheets/{sid}/export.pdf?view=v_lv_0&paper=A1&ratio=100", headers=H)
    text = pymupdf.open(stream=pdf.content)[0].get_text()
    assert "SKALA 1:100" in text and "102 Kök" in text and "KV DN28" in text
    # och när allt är gjort: dokumentet är fortfarande giltigt, med sina ursprung
    d = client.get(f"/api/cad/sheets/{sid}", headers=H).json()["content"]
    assert client.post("/api/cad/validate", json={"content": d}, headers=H).json()["problems"] == []
    prov = {e["provenance"] for e in d["entities"]}
    assert prov == {"USER_MODELLED", "AGENT_CREATED_APPROVED"}
