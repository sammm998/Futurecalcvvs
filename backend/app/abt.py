"""ABT 06: rummen i ett projekt, lästa ur A-planernas rumsetiketter (vvs_engine/abt/rooms).

En ritning läses på sina rum när någon ber om det. Varje rumsetikett blir ett rum i projektet - nummer, namn eller
lägenhetstyp, och arean som står skriven - med sida och plats på bladet, så att varje rad går att visa där den kom
ifrån. Raderna är RÄKNADE: läsningen räknade dem på bladet, den mätte dem inte.

Samma plan förekommer ofta på flera blad - en våning i både sanitets- och värmeritningen. En sida vars etiketter
står exakt som på en tidigare sida räknas inte en gång till, och det står vid sidan. Den som kalkylerar avgör: en
sida kan räknas eller lämnas, och beslutet står kvar vid rummen.

Samma läsning räknar enheterna - koderna vid inredningen - och symbolerna som upprepas (vvs_engine/abt/units och
symbols). En symbol räknas först när den har ett namn: bladets egen förklaring eller det användaren säger.

Priset är det som beslutades för ABT 06 (docs/abt06-plan.md, Credits): bladpriset för varje sida där läsningen
hittar rum, enheter eller symboler, visat innan läsningen och draget en gång per ritning. En ritning utan något av
det kostar ingenting. Administratören kan sätta läsningen till en annan andel av bladpriset (`rooms_factor`).
"""
from __future__ import annotations

import csv
import io
import json
import re
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from . import credits as credits_api
from .auth import current_user
from .db import CreditEntry, Drawing, Markup, Project, ProjectEstimate, Space, User, get_db
from .storage import storage

router = APIRouter(prefix="/api", tags=["abt06"])

READ_BY = "rumsläsare"          # rooms the reader wrote; a person's own rooms are never replaced by a new reading
UNITS_BY = "enhetsläsare"       # units the reader counted, each a count marker the person can move or remove
UNITS_LAYER = "ABT enheter"     # the takeoff tool's layer they lie on, so they can be shown, hidden and reviewed
SYMBOLS_BY = "symbolläsare"     # copies of a named symbol, each a count marker like a unit
SYMBOLS_LAYER = "ABT symboler"
CHARGE_KIND = "rumslasning"
SYMBOL_ID = re.compile(r"^sym:[0-9a-f]{10}(?:-\d{1,3})?$")


def _project(db: Session, user: User, project_id: str) -> Project:
    p = db.get(Project, project_id)
    if p is None or p.owner_id != user.id:
        raise HTTPException(404, "Projektet finns inte")
    return p


def _drawing(db: Session, user: User, drawing_id: str) -> Drawing:
    d = db.get(Drawing, drawing_id)
    if d is None or d.project.owner_id != user.id:
        raise HTTPException(404, "Ritningen finns inte")
    return d


def _kept(d: Drawing, name: str) -> str:
    return f"results/{d.id}/abt/{name}"


def _load(key: str) -> dict | None:
    if not storage.exists(key):
        return None
    try:
        with storage.open(key) as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def _save(key: str, data: dict) -> None:
    storage.put(key, io.BytesIO(json.dumps(data, ensure_ascii=False).encode("utf-8")))


def _read(d: Drawing) -> dict[str, Any]:
    """The drawing read on rooms, units and symbols - once: the price and the reading share it, and a large set
    of plans takes a while to read."""
    from vvs_engine.abt import READER, read_document
    got = _load(_kept(d, "reading.json"))
    if not got or got.get("reader") != READER or got.get("sha256") != (d.sha256 or ""):
        try:
            got = read_document(storage.path(d.storage_key))
        except Exception as e:                   # noqa: BLE001 - a file that cannot be opened is said, not raised
            raise HTTPException(422, f"Ritningen kunde inte läsas på rum: {type(e).__name__}")
        got["sha256"] = d.sha256 or ""
        _save(_kept(d, "reading.json"), got)
    got["by_page"] = {int(k): v for k, v in (got.get("by_page") or {}).items()}
    return got


def _priced(got: dict) -> list[int]:
    return list(got.get("priced_pages") or [p["page"] for p in got["pages"]])


def _repeated(symbols: list[dict] | None) -> list[dict]:
    """The groups worth showing from one drawing alone: repeated in it, or named by its own legend."""
    from vvs_engine.abt.symbols import MIN_REPEAT
    return [g for g in symbols or [] if g["count"] >= MIN_REPEAT or g.get("legend")]


def _quote(db: Session, d: Drawing, pages: list[int]) -> dict[str, Any]:
    """The sheet price of the pages that have rooms, and nothing for the rest."""
    pl = credits_api.price_list(db)
    measured = credits_api.measure_pages(storage.path(d.storage_key), d.sha256)
    rows = credits_api.quote_pages([dict(measured[p], raster=False) for p in pages if p < len(measured)], pl)
    factor = float(pl.get("rooms_factor", 1.0) or 0.0)
    for r, p in zip(rows["pages"], pages):
        r["page"] = p
        r["credits"] = round(r["credits"] * factor, 2)
    rows["credits"] = round(rows["credits"] * factor, 2)
    return rows


def _charged(db: Session, d: Drawing) -> bool:
    return db.query(CreditEntry).filter(CreditEntry.ref == f"rooms:{d.id}", CreditEntry.kind == CHARGE_KIND).first() is not None


@router.get("/drawings/{drawing_id}/rooms/price")
def rooms_price(drawing_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    d = _drawing(db, user, drawing_id)
    got = _read(d)
    pages = _priced(got)
    q = _quote(db, d, pages)
    already = _charged(db, d)
    exempt = credits_api.is_exempt(user)
    return {"drawing_id": d.id, "pages_with_rooms": [p["page"] for p in got["pages"]], "pages_priced": pages,
            "credits": 0.0 if (already or exempt) else q["credits"],
            "sheet_credits": q["credits"], "already_paid": already, "exempt": exempt,
            "labels": got["labels"], "units": len(got.get("units", [])), "symbols": len(_repeated(got.get("symbols"))),
            "balance": credits_api.balance(db, user)}


@router.post("/drawings/{drawing_id}/rooms")
def read_rooms(drawing_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Read the drawing's rooms and put them in the project, in place of what an earlier reading put there."""
    d = _drawing(db, user, drawing_id)
    got = _read(d)
    pages = _priced(got)
    if pages and not credits_api.is_exempt(user) and not _charged(db, d):
        q = _quote(db, d, pages)
        key = credits_api.owner_key(user)
        need = credits_api._cc(q["credits"])
        have = credits_api.balance_cc(db, key)
        if have < need:
            raise HTTPException(402, {"message": f"Rumsläsningen kostar {q['credits']:g} credits och kontot har {have / 100:g}.",
                                      "credits": q["credits"], "balance": have / 100, "missing": (need - have) / 100})
        credits_api.post(db, user, key, -q["credits"], CHARGE_KIND, ref=f"rooms:{d.id}",
                         note=f"Rum, enheter och symboler ur {d.filename}: {len(pages)} sidor")
    # an earlier reading of this drawing is replaced; what a person entered is kept
    for s in db.query(Space).filter(Space.drawing_id == d.id).all():
        if (s.props or {}).get("read_by") == READ_BY:
            db.delete(s)
    db.flush()
    # a page that repeats a page already read in the project - this drawing or another - is not counted again
    earlier = _signatures(db, d.project_id)
    for p in got["pages"]:
        where = earlier.get(p["signature"])
        if where is not None and p["same_as"] is None:
            p["same_as_elsewhere"] = where
            p["counted"] = False
        earlier.setdefault(p["signature"], {"drawing_id": d.id, "page": p["page"], "filename": d.filename})
    # the units: an earlier reading's markers go, a person's own markers stay
    for m in db.query(Markup).filter(Markup.drawing_id == d.id).all():
        if (m.props or {}).get("read_by") == UNITS_BY:
            db.delete(m)
    for u in got.get("units", []):
        x0, y0, x1, y1 = u["bbox"]
        db.add(Markup(drawing_id=d.id, user_id=user.id, page=u["page"], tool="antal", layer=UNITS_LAYER,
                      designation=u["code"], points=[[round((x0 + x1) / 2, 2), round((y0 + y1) / 2, 2)]],
                      subject=u["name"] or "", status="oppen",
                      props={"read_by": UNITS_BY, "source_type": "RÄKNAD", "bbox": u["bbox"], "code": u["code"],
                             "name_source": u["name_source"]},
                      meta={"abt": True}))
    legend = {k: {**v, "drawing_id": d.id, "filename": d.filename} for k, v in (got.get("legend") or {}).items()}
    counted = {p["page"]: p["counted"] for p in got["pages"]}
    sigs = {p["page"]: p["signature"] for p in got["pages"]}
    for pno, rooms in got["by_page"].items():
        for r in rooms:
            db.add(Space(project_id=d.project_id, drawing_id=d.id, page=pno, kind=r["kind"], name=r["name"] or "",
                         code=r["number"] or "", ring=[], user_id=user.id,
                         props={"read_by": READ_BY, "source_type": "RÄKNAD", "area_m2": r["area_m2"],
                                "area_text": r["area_text"], "area_source": "text", "apartment": r["apartment"],
                                "bbox": r["bbox"], "lines": r["lines"], "counted": counted.get(pno, True),
                                "signature": sigs.get(pno)}))
    db.commit()
    _remember_legend(db, d.project_id, legend)
    # the symbols: what this reading found is kept with the drawing, and the named ones are counted - here, and
    # in the project's other drawings when this one's legend names a symbol they have too
    symbols = got.get("symbols") or []
    _save(_kept(d, "symbols.json"), {"drawing_id": d.id, "sha256": d.sha256 or "", "symbols": symbols})
    _thumbnails(d, symbols)
    project = db.get(Project, d.project_id)
    kept = _kept_symbols(project)
    names = _symbol_names(db, project, kept)
    named = _sync_symbols(db, user, d, symbols, names, fresh=True)
    for other in project.drawings:
        if other.id != d.id and other.id in kept:
            _sync_symbols(db, user, other, kept[other.id], names)
    db.commit()
    return {"drawing_id": d.id, "pages": got["pages"], "labels": got["labels"],
            "totals": got["totals"], "apartments": got["apartments"], "units": len(got.get("units", [])),
            "symbols": len(_repeated(symbols)), "named_symbols": named}


def _signatures(db: Session, project_id: str) -> dict[str, dict]:
    """The pages already read in the project, by what their labels say: signature -> where it was read first."""
    names = {d.id: d.filename for d in db.query(Drawing).filter(Drawing.project_id == project_id).all()}
    out: dict[str, dict] = {}
    rows = (db.query(Space).filter(Space.project_id == project_id).order_by(Space.created_at).all())
    for s in rows:
        props = s.props or {}
        sig = props.get("signature")
        if props.get("read_by") == READ_BY and sig and sig not in out:
            out[sig] = {"drawing_id": s.drawing_id, "page": s.page, "filename": names.get(s.drawing_id)}
    return out



def _room_out(s: Space, filename: str) -> dict[str, Any]:
    p = s.props or {}
    return {"id": s.id, "drawing_id": s.drawing_id, "filename": filename, "page": s.page, "kind": s.kind,
            "number": s.code or None, "name": s.name or None, "apartment": p.get("apartment"),
            "area_m2": p.get("area_m2"), "area_text": p.get("area_text"), "bbox": p.get("bbox"),
            "lines": p.get("lines"), "counted": bool(p.get("counted", True)), "source_type": p.get("source_type", "RÄKNAD"),
            "read_by": p.get("read_by")}


def project_rooms(db: Session, project: Project) -> dict[str, Any]:
    from vvs_engine.abt.rooms import register
    names = {d.id: d.filename for d in project.drawings}
    spaces = (db.query(Space).filter(Space.project_id == project.id, Space.kind.in_(("rum", "lagenhet", "summa")))
              .order_by(Space.drawing_id, Space.page).all())
    rows = [_room_out(s, names.get(s.drawing_id, "")) for s in spaces]
    pages: dict[tuple, dict] = {}
    for r, s in zip(rows, spaces):
        k = (r["drawing_id"], r["page"])
        e = pages.setdefault(k, {"drawing_id": r["drawing_id"], "filename": r["filename"], "page": r["page"],
                                 "rooms": 0, "apartments": 0, "area_m2": 0.0, "counted": r["counted"],
                                 "signature": (s.props or {}).get("signature")})
        if r["kind"] == "rum":
            e["rooms"] += 1
        elif r["kind"] == "lagenhet":
            e["apartments"] += 1
        if r["kind"] != "summa":
            e["area_m2"] = round(e["area_m2"] + (r["area_m2"] or 0.0), 2)
    first: dict[str, dict] = {}
    for e in pages.values():
        if e["signature"] in first:
            e["same_as"] = {k: first[e["signature"]][k] for k in ("drawing_id", "filename", "page")}
        else:
            first[e["signature"]] = e
            e["same_as"] = None
    counted = [dict(r, where={"drawing_id": r["drawing_id"], "page": r["page"]}) for r in rows if r["counted"]]
    reg = register(counted)
    return {"project_id": project.id, "contract_form": project.contract_form or "AB04", "pages": list(pages.values()),
            "rooms": rows, "register": {"apartments": reg["apartments"], "totals": reg["totals"]},
            "source_type": "RÄKNAD",
            "read": [d.id for d in project.drawings if storage.exists(_kept(d, "symbols.json"))]}


@router.get("/projects/{project_id}/rooms")
def get_project_rooms(project_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return project_rooms(db, _project(db, user, project_id))


class PageChoice(BaseModel):
    drawing_id: str
    page: int
    counted: bool


@router.patch("/projects/{project_id}/rooms/pages")
def choose_page(project_id: str, body: PageChoice, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Count a page's rooms, or leave them out - the person who prices the project decides which plans are its."""
    p = _project(db, user, project_id)
    d = _drawing(db, user, body.drawing_id)
    if d.project_id != p.id:
        raise HTTPException(404, "Ritningen finns inte i projektet")
    spaces = db.query(Space).filter(Space.drawing_id == d.id, Space.page == body.page).all()
    if not spaces:
        raise HTTPException(404, "Sidan har inga lästa rum")
    for s in spaces:
        s.props = {**(s.props or {}), "counted": body.counted}
    db.commit()
    return project_rooms(db, p)


@router.get("/projects/{project_id}/rooms.csv")
def export_rooms(project_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """The project's rooms as a list a calculation can take: every room with where it was read and how."""
    out = project_rooms(db, _project(db, user, project_id))
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["källtyp", "ritning", "sida", "slag", "rumsnummer", "namn", "lägenhetstyp", "area_m2", "areatext",
                "räknas"])
    for r in out["rooms"]:
        w.writerow([r["source_type"], r["filename"], r["page"] + 1, r["kind"], r["number"] or "", r["name"] or "",
                    (r["apartment"] or {}).get("text", ""), f"{(r['area_m2'] or 0):.2f}".replace(".", ","),
                    r["area_text"] or "", "ja" if r["counted"] else "nej"])
    name = "".join(c for c in out["project_id"] if c.isalnum())[:12]
    return Response(("﻿" + buf.getvalue()).encode("utf-8"), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="rum-{name}.csv"'})


# ------------------------------------------------------------------------------------------------------------
# Enheterna: koderna arkitekten skriver vid inredningen (vvs_engine/abt/units)
# ------------------------------------------------------------------------------------------------------------

LEGENDS = "_legends"            # the sheets' own legends, kept beside the names a person gave


def _estimate(db: Session, project_id: str) -> ProjectEstimate:
    est = db.query(ProjectEstimate).filter(ProjectEstimate.project_id == project_id).first()
    if est is None:
        est = ProjectEstimate(project_id=project_id, unit_names={})
        db.add(est)
        db.flush()
    return est


def _remember_legend(db: Session, project_id: str, legend: dict[str, dict]) -> None:
    if not legend:
        return
    est = _estimate(db, project_id)
    names = dict(est.unit_names or {})
    kept = dict(names.get(LEGENDS) or {})
    for code, entry in legend.items():
        kept.setdefault(code, entry)
    names[LEGENDS] = kept
    est.unit_names = names
    db.commit()


def project_units(db: Session, project: Project) -> dict[str, Any]:
    """Every unit code in the project, counted on the pages that are counted, named by the person, the sheets'
    legends or the reference data - or not at all."""
    from vvs_engine.abt.units import name_of
    est = db.query(ProjectEstimate).filter(ProjectEstimate.project_id == project.id).first()
    stored = dict((est.unit_names if est else None) or {})
    legends = stored.pop(LEGENDS, {}) or {}
    given = {k: v for k, v in stored.items() if isinstance(v, str)}
    names = {d.id: d.filename for d in project.drawings}
    counted_pages = {(s.drawing_id, s.page): bool((s.props or {}).get("counted", True))
                     for s in db.query(Space).filter(Space.project_id == project.id).all()
                     if (s.props or {}).get("read_by") == READ_BY}
    marks = (db.query(Markup).filter(Markup.drawing_id.in_(list(names) or [""]), Markup.layer == UNITS_LAYER,
                                     Markup.deleted.is_(False))
             .order_by(Markup.drawing_id, Markup.page).all())
    codes: dict[str, dict] = {}
    for m in marks:
        if (m.props or {}).get("read_by") != UNITS_BY or m.status == "avvisad":
            continue
        code = m.designation or ""
        e = codes.setdefault(code, {"code": code, "count": 0, "not_counted": 0, "pages": []})
        if counted_pages.get((m.drawing_id, m.page), True):
            e["count"] += 1
            where = {"drawing_id": m.drawing_id, "filename": names.get(m.drawing_id), "page": m.page}
            if where not in e["pages"]:
                e["pages"].append(where)
        else:
            e["not_counted"] += 1
    rows = []
    for code, e in sorted(codes.items(), key=lambda kv: (-kv[1]["count"], kv[0])):
        name, source = name_of(code, {k: v.get("term") for k, v in legends.items()}, given)
        legend = legends.get(code) if source == "bladets förklaring" else None
        rows.append({**e, "name": name, "name_source": source, "source_type": "RÄKNAD",
                     "legend": {"filename": legend.get("filename"), "page": legend.get("page")} if legend else None})
    return {"project_id": project.id, "units": rows, "layer": UNITS_LAYER,
            "totals": {"codes": len(rows), "named": sum(1 for r in rows if r["name"]),
                       "units": sum(r["count"] for r in rows)}}


@router.get("/projects/{project_id}/units")
def get_project_units(project_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return project_units(db, _project(db, user, project_id))


class UnitName(BaseModel):
    code: str
    name: str


@router.put("/projects/{project_id}/units/names")
def name_unit(project_id: str, body: UnitName, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """A person says what a code is. That goes before the sheet's legend and the reference data - she is the one
    who has the architect's legend in front of her. An empty name takes it back."""
    p = _project(db, user, project_id)
    code = body.code.strip()
    if not code or code == LEGENDS or len(code) > 16 or SYMBOL_ID.match(code):
        raise HTTPException(422, "Okänd kod")
    est = _estimate(db, p.id)
    names = dict(est.unit_names or {})
    if body.name.strip():
        names[code] = body.name.strip()[:120]
    else:
        names.pop(code, None)
    est.unit_names = names
    db.commit()
    return project_units(db, p)


@router.get("/projects/{project_id}/units.csv")
def export_units(project_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    out = project_units(db, _project(db, user, project_id))
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["källtyp", "kod", "namn", "namnet enligt", "antal", "sidor"])
    for r in out["units"]:
        w.writerow([r["source_type"], r["code"], r["name"] or "", r["name_source"], r["count"],
                    ", ".join(f"{p['filename']} s.{p['page'] + 1}" for p in r["pages"])])
    name = "".join(c for c in out["project_id"] if c.isalnum())[:12]
    return Response(("\ufeff" + buf.getvalue()).encode("utf-8"), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="enheter-{name}.csv"'})


# ------------------------------------------------------------------------------------------------------------
# Symbolerna: upprepade block, räknade först när de har ett namn (vvs_engine/abt/symbols)
# ------------------------------------------------------------------------------------------------------------

THUMB_PX = 160          # the longest side of a symbol's picture in the gallery


def _safe(symbol_id: str) -> str:
    return symbol_id.replace(":", "_")


def _kept_symbols(project: Project) -> dict[str, list[dict]]:
    """What the readings found, drawing by drawing: only drawings that have been read have any."""
    out: dict[str, list[dict]] = {}
    for d in project.drawings:
        kept = _load(_kept(d, "symbols.json"))
        if kept is not None:
            out[d.id] = kept.get("symbols") or []
    return out


def _symbol_names(db: Session, project: Project, kept: dict[str, list[dict]]) -> dict[str, tuple[str, str]]:
    """Every symbol in the project that has a name, and who gave it: the person first, then a sheet's own legend -
    in any of the project's drawings, as with the codes. Nobody else names a symbol."""
    est = db.query(ProjectEstimate).filter(ProjectEstimate.project_id == project.id).first()
    out: dict[str, tuple[str, str]] = {}
    for groups in kept.values():
        for g in groups:
            if g.get("legend") and g["id"] not in out:
                out[g["id"]] = (g["legend"]["term"], "bladets förklaring")
    for k, v in ((est.unit_names if est else None) or {}).items():
        if isinstance(v, str) and v and SYMBOL_ID.match(k):
            out[k] = (v, "angiven")
    return out


def _sync_symbols(db: Session, user: User, d: Drawing, symbols: list[dict], names: dict[str, tuple[str, str]],
                  only: str | None = None, fresh: bool = False) -> int:
    """A count marker for every copy of a symbol with a name, none for the rest.

    A fresh reading puts the copies where it found them. Otherwise a symbol keeps its markers where they are - a
    marker someone moved or rejected keeps its place and its verdict - and only takes a new name; a symbol that
    lost its name loses its markers, and one that got a name gets them."""
    have: dict[str, list[Markup]] = {}
    for m in db.query(Markup).filter(Markup.drawing_id == d.id, Markup.layer == SYMBOLS_LAYER).all():
        props = m.props or {}
        if props.get("read_by") == SYMBOLS_BY and (only is None or props.get("symbol") == only):
            have.setdefault(props.get("symbol") or "", []).append(m)
    named = 0
    for g in symbols:
        if only is not None and g["id"] != only:
            continue
        name, source = names.get(g["id"], (None, None))
        mine = have.pop(g["id"], [])
        if name:
            named += 1
        if name and mine and not fresh:
            for m in mine:
                m.designation, m.subject = name, name
                m.props = {**(m.props or {}), "name_source": source}
            continue
        for m in mine:
            db.delete(m)
        if not name:
            continue
        for s in g["instances"]:
            x0, y0, x1, y1 = s["bbox"]
            db.add(Markup(drawing_id=d.id, user_id=user.id, page=s["page"], tool="antal", layer=SYMBOLS_LAYER,
                          designation=name, points=[[round((x0 + x1) / 2, 2), round((y0 + y1) / 2, 2)]],
                          subject=name, status="oppen",
                          props={"read_by": SYMBOLS_BY, "source_type": "RÄKNAD", "bbox": s["bbox"],
                                 "symbol": g["id"], "name_source": source},
                          meta={"abt": True}))
    if only is None:
        for gone in have.values():               # a symbol the drawing's reading no longer has
            for m in gone:
                db.delete(m)
    return named


def _thumbnails(d: Drawing, symbols: list[dict]) -> None:
    """A picture of the first copy of every symbol, drawn while the document is open: the gallery shows them, and
    a page of a large set is laid out once for all its pictures."""
    import pymupdf
    want: dict[int, list[tuple[str, list]]] = {}
    for g in _repeated(symbols):
        s = g["instances"][0]
        want.setdefault(s["page"], []).append((g["id"], s["bbox"]))
    storage.delete_prefix(_kept(d, "sym"))
    with pymupdf.open(storage.path(d.storage_key)) as doc:
        for pno, items in want.items():
            page = doc[pno]
            shown = page.get_displaylist()
            for sid, bbox in items:
                _picture(d, page, shown, sid, bbox)


def _picture(d: Drawing, page, shown, sid: str, bbox: list) -> bytes | None:
    import pymupdf
    x0, y0, x1, y1 = bbox
    pad = max(2.0, 0.08 * max(x1 - x0, y1 - y0))
    r = (pymupdf.Rect(x0 - pad, y0 - pad, x1 + pad, y1 + pad) * page.rotation_matrix) & page.rect
    if r.is_empty:
        return None
    z = min(8.0, THUMB_PX / max(r.width, r.height, 1.0))
    png = shown.get_pixmap(matrix=pymupdf.Matrix(z, z), clip=r, alpha=False).tobytes("png")
    storage.put(_kept(d, f"sym/{_safe(sid)}.png"), io.BytesIO(png))
    return png


BESIDE = 0.75           # of a symbol's size: a code written this close to a copy is the code of that copy


def _beside_codes(db: Session, project: Project, counted_pages: dict) -> dict[str, dict]:
    """The copies of each named symbol that stand where a code for the same thing is written - the code itself,
    or the name the code goes by: one unit drawn and labelled, not two. Each code stands by one copy at most."""
    code_names = {u["code"]: u.get("name") or "" for u in project_units(db, project)["units"]}
    ids = [d.id for d in project.drawings] or [""]
    codes: dict[tuple, list[list]] = {}
    for m in db.query(Markup).filter(Markup.drawing_id.in_(ids), Markup.layer == UNITS_LAYER, Markup.deleted.is_(False)).all():
        if (m.props or {}).get("read_by") != UNITS_BY or m.status == "avvisad" or not m.points:
            continue
        if counted_pages.get((m.drawing_id, m.page), True):
            codes.setdefault((m.drawing_id, m.page), []).append([m.points[0][0], m.points[0][1], m.designation or "", False])
    out: dict[str, dict] = {}
    same = lambda a, b: bool(a) and bool(b) and a.strip().casefold() == b.strip().casefold()  # noqa: E731
    for m in db.query(Markup).filter(Markup.drawing_id.in_(ids), Markup.layer == SYMBOLS_LAYER, Markup.deleted.is_(False)).all():
        props = m.props or {}
        if props.get("read_by") != SYMBOLS_BY or m.status == "avvisad" or not props.get("bbox"):
            continue
        if not counted_pages.get((m.drawing_id, m.page), True):
            continue
        x0, y0, x1, y1 = props["bbox"]
        reach = BESIDE * max(x1 - x0, y1 - y0)
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        near = [c for c in codes.get((m.drawing_id, m.page), []) if not c[3]
                and (same(c[2], m.designation) or same(code_names.get(c[2]), m.designation))
                and x0 - reach <= c[0] <= x1 + reach and y0 - reach <= c[1] <= y1 + reach]
        if near:
            c = min(near, key=lambda c: (c[0] - cx) ** 2 + (c[1] - cy) ** 2)
            c[3] = True
            e = out.setdefault(props.get("symbol") or "", {"code": c[2], "count": 0})
            e["count"] += 1
    return out


def project_symbols(db: Session, project: Project) -> dict[str, Any]:
    """Every symbol the readings found in the project. A named one is counted from its markers - what was rejected
    or removed in the takeoff is not - on the pages that are counted; one without a name is shown with how many
    copies the reading found, and is not counted."""
    names = {d.id: d.filename for d in project.drawings}
    kept = _kept_symbols(project)
    named_as = _symbol_names(db, project, kept)
    counted_pages = {(s.drawing_id, s.page): bool((s.props or {}).get("counted", True))
                     for s in db.query(Space).filter(Space.project_id == project.id).all()
                     if (s.props or {}).get("read_by") == READ_BY}
    groups: dict[str, dict] = {}
    for d in project.drawings:
        for g in kept.get(d.id, []):
            e = groups.setdefault(g["id"], {"id": g["id"], "size": g["size"], "parts": g["parts"], "legend": None,
                                            "found": 0, "found_not_counted": 0, "pages": [], "sample": None})
            first = g["instances"][0]
            if e["sample"] is None:
                e["sample"] = {"drawing_id": d.id, "filename": d.filename, "page": first["page"], "bbox": first["bbox"]}
            if g.get("legend") and e["legend"] is None:
                e["legend"] = {**g["legend"], "drawing_id": d.id, "filename": d.filename}
            for s in g["instances"]:
                if counted_pages.get((d.id, s["page"]), True):
                    e["found"] += 1
                    where = {"drawing_id": d.id, "filename": d.filename, "page": s["page"]}
                    if where not in e["pages"]:
                        e["pages"].append(where)
                else:
                    e["found_not_counted"] += 1
    counted: dict[str, int] = {}
    not_counted: dict[str, int] = {}
    marks = (db.query(Markup).filter(Markup.drawing_id.in_(list(names) or [""]), Markup.layer == SYMBOLS_LAYER,
                                     Markup.deleted.is_(False)).all())
    for m in marks:
        props = m.props or {}
        if props.get("read_by") != SYMBOLS_BY or m.status == "avvisad":
            continue
        sid = props.get("symbol") or ""
        if counted_pages.get((m.drawing_id, m.page), True):
            counted[sid] = counted.get(sid, 0) + 1
        else:
            not_counted[sid] = not_counted.get(sid, 0) + 1
    rows = []
    for sid, e in groups.items():
        name, source = named_as.get(sid, (None, None))
        found, extra = e.pop("found"), e.pop("found_not_counted")
        rows.append({**e, "name": name, "name_source": source, "counted": bool(name), "source_type": "RÄKNAD",
                     "count": counted.get(sid, 0) if name else found,
                     "not_counted": not_counted.get(sid, 0) if name else extra})
    from vvs_engine.abt.symbols import MIN_REPEAT
    rows = [r for r in rows if r["counted"] or r["count"] + r["not_counted"] >= MIN_REPEAT]
    beside = _beside_codes(db, project, counted_pages) if any(r["counted"] for r in rows) else {}
    for r in rows:
        r["beside_code"] = beside.get(r["id"]) if r["counted"] else None
    rows.sort(key=lambda r: (not r["counted"], -r["count"], r["id"]))
    named = [r for r in rows if r["counted"]]
    return {"project_id": project.id, "symbols": rows, "layer": SYMBOLS_LAYER,
            "read": len(kept),
            "totals": {"groups": len(rows), "named": len(named), "symbols": sum(r["count"] for r in named)}}


@router.get("/projects/{project_id}/symbols")
def get_project_symbols(project_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return project_symbols(db, _project(db, user, project_id))


class SymbolName(BaseModel):
    id: str
    name: str


@router.put("/projects/{project_id}/symbols/names")
def name_symbol(project_id: str, body: SymbolName, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """A person says what a symbol is - "det här är WC" - and from then on every copy of it in the project is
    counted, in every drawing that has it. An empty name takes it back."""
    p = _project(db, user, project_id)
    sid = body.id.strip()
    if not SYMBOL_ID.match(sid):
        raise HTTPException(422, "Okänd symbol")
    est = _estimate(db, p.id)
    names = dict(est.unit_names or {})
    if body.name.strip():
        names[sid] = body.name.strip()[:120]
    else:
        names.pop(sid, None)
    est.unit_names = names
    db.flush()
    kept = _kept_symbols(p)
    named_as = _symbol_names(db, p, kept)
    for d in p.drawings:
        if d.id in kept:
            _sync_symbols(db, user, d, kept[d.id], named_as, only=sid)
    db.commit()
    return project_symbols(db, p)


@router.get("/drawings/{drawing_id}/symbols/{symbol_id}.png")
def symbol_picture(drawing_id: str, symbol_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """The picture of a symbol's first copy in the drawing - drawn when the drawing was read, or now for a symbol
    that is repeated only over the project's drawings."""
    d = _drawing(db, user, drawing_id)
    if not SYMBOL_ID.match(symbol_id):
        raise HTTPException(404, "Symbolen finns inte")
    key = _kept(d, f"sym/{_safe(symbol_id)}.png")
    data = None
    if storage.exists(key):
        with storage.open(key) as fh:
            data = fh.read()
    else:
        g = next((g for g in (_load(_kept(d, "symbols.json")) or {}).get("symbols") or [] if g["id"] == symbol_id), None)
        if g is not None:
            import pymupdf
            s = g["instances"][0]
            with pymupdf.open(storage.path(d.storage_key)) as doc:
                page = doc[s["page"]]
                data = _picture(d, page, page.get_displaylist(), symbol_id, s["bbox"])
    if data is None:
        raise HTTPException(404, "Symbolen finns inte")
    return Response(data, media_type="image/png", headers={"Cache-Control": "private, max-age=3600"})


@router.get("/projects/{project_id}/symbols.csv")
def export_symbols(project_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """The named symbols as a list a calculation can take; a symbol without a name is not counted and not listed."""
    out = project_symbols(db, _project(db, user, project_id))
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["källtyp", "symbol", "namn", "namnet enligt", "antal", "sidor"])
    for r in out["symbols"]:
        if not r["counted"]:
            continue
        w.writerow([r["source_type"], r["id"], r["name"], r["name_source"], r["count"],
                    ", ".join(f"{p['filename']} s.{p['page'] + 1}" for p in r["pages"])])
    name = "".join(c for c in out["project_id"] if c.isalnum())[:12]
    return Response(("﻿" + buf.getvalue()).encode("utf-8"), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="symboler-{name}.csv"'})
