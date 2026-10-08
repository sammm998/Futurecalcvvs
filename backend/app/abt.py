"""ABT 06: rummen i ett projekt, lästa ur A-planernas rumsetiketter (vvs_engine/abt/rooms).

En ritning läses på sina rum när någon ber om det. Varje rumsetikett blir ett rum i projektet - nummer, namn eller
lägenhetstyp, och arean som står skriven - med sida och plats på bladet, så att varje rad går att visa där den kom
ifrån. Raderna är RÄKNADE: läsningen räknade dem på bladet, den mätte dem inte.

Samma plan förekommer ofta på flera blad - en våning i både sanitets- och värmeritningen. En sida vars etiketter
står exakt som på en tidigare sida räknas inte en gång till, och det står vid sidan. Den som kalkylerar avgör: en
sida kan räknas eller lämnas, och beslutet står kvar vid rummen.

Priset är det som beslutades för ABT 06 (docs/abt06-plan.md, Credits): bladpriset för varje sida som har rum, visat
innan läsningen och draget en gång per ritning. En ritning utan ett enda rum kostar ingenting. Administratören kan
sätta rumsläsningen till en annan andel av bladpriset (`rooms_factor`).
"""
from __future__ import annotations

import csv
import io
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from . import credits as credits_api
from .auth import current_user
from .db import CreditEntry, Drawing, Project, Space, User, get_db
from .storage import storage

router = APIRouter(prefix="/api", tags=["abt06"])

READ_BY = "rumsläsare"          # rooms the reader wrote; a person's own rooms are never replaced by a new reading
CHARGE_KIND = "rumslasning"


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


def _read(d: Drawing) -> dict[str, Any]:
    from vvs_engine.abt.rooms import read_document
    try:
        return read_document(storage.path(d.storage_key))
    except Exception as e:                       # noqa: BLE001 - a file that cannot be opened is said, not raised
        raise HTTPException(422, f"Ritningen kunde inte läsas på rum: {type(e).__name__}")


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
    pages = [p["page"] for p in got["pages"]]
    q = _quote(db, d, pages)
    already = _charged(db, d)
    exempt = credits_api.is_exempt(user)
    return {"drawing_id": d.id, "pages_with_rooms": pages, "credits": 0.0 if (already or exempt) else q["credits"],
            "sheet_credits": q["credits"], "already_paid": already, "exempt": exempt,
            "labels": got["labels"], "balance": credits_api.balance(db, user)}


@router.post("/drawings/{drawing_id}/rooms")
def read_rooms(drawing_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Read the drawing's rooms and put them in the project, in place of what an earlier reading put there."""
    d = _drawing(db, user, drawing_id)
    got = _read(d)
    pages = [p["page"] for p in got["pages"]]
    if pages and not credits_api.is_exempt(user) and not _charged(db, d):
        q = _quote(db, d, pages)
        key = credits_api.owner_key(user)
        need = credits_api._cc(q["credits"])
        have = credits_api.balance_cc(db, key)
        if have < need:
            raise HTTPException(402, {"message": f"Rumsläsningen kostar {q['credits']:g} credits och kontot har {have / 100:g}.",
                                      "credits": q["credits"], "balance": have / 100, "missing": (need - have) / 100})
        credits_api.post(db, user, key, -q["credits"], CHARGE_KIND, ref=f"rooms:{d.id}",
                         note=f"Rum ur {d.filename}: {len(pages)} sidor med rum")
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
    return {"drawing_id": d.id, "pages": got["pages"], "labels": got["labels"],
            "totals": got["totals"], "apartments": got["apartments"]}


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


def forget_drawing(db: Session, drawing_id: str) -> None:
    """The rooms read from a drawing go with it."""
    db.query(Space).filter(Space.drawing_id == drawing_id).delete(synchronize_session=False)


def forget_project(db: Session, project_id: str) -> None:
    db.query(Space).filter(Space.project_id == project_id).delete(synchronize_session=False)


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
            "source_type": "RÄKNAD"}


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
