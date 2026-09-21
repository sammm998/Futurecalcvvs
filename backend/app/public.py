"""Det gränssnittet skickar in, och det gränssnittet får ut utan att vara admin.

Tre saker: vilken variant av ett pågående prov den här besökaren ska se, vad besökaren gjorde, och texten på en
sida som någon redigerat i CMS:et.

Om det som skickas in: en händelse är en ruta och en sidväg, inte en person. Koordinaterna är andelar av
fönstret så att en heatmap gäller alla skärmstorlekar, och det finns ingenting i raden som gör den till en logg
över någons arbetsdag. Sessionsnyckeln kommer från webbläsaren, byts när fliken stängs, och finns bara för att
kunna räkna en besökare en gång i ett prov i stället för en gång per klick.
"""
from __future__ import annotations

import datetime as dt
import hashlib

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .auth import current_user
from .db import Content, Event, Experiment, User, get_db

router = APIRouter(prefix="/api", tags=["public"])

MAX_EVENTS = 60          # per anrop: gränssnittet samlar ihop och skickar sällan
EVENT_NAMES = {"klick", "sidvisning", "mal"}


def variant_for(key: str, session: str, split_b: float) -> str:
    """Vilken sida av provet den här besökaren hamnar på.

    Avgjort av en hash av nyckeln och sessionen, inte av en slump. En slump skulle ge samma besökare olika
    varianter vid varje sidladdning, och ett prov där en person ser båda sidorna mäter ingenting.
    """
    h = hashlib.sha256(f"{key}:{session}".encode("utf-8")).digest()
    return "b" if int.from_bytes(h[:4], "big") / 0xFFFFFFFF < max(0.0, min(1.0, split_b)) else "a"


@router.get("/experiments/active")
def active_experiments(session: str, db: Session = Depends(get_db)):
    """Vilka prov som pågår och vad den här besökaren ska se av dem."""
    if not session or len(session) > 64:
        raise HTTPException(400, "Ogiltig sessionsnyckel")
    out = {}
    for e in db.query(Experiment).filter(Experiment.status == "igang").all():
        v = variant_for(e.key, session, e.split_b)
        out[e.key] = {"variant": v, "label": (e.variants or {}).get(v, v.upper()), "goal": e.goal_event}
    return {"experiments": out}


class EventIn(BaseModel):
    name: str
    path: str = ""
    x: float | None = None
    y: float | None = None
    target: str = ""
    experiment: str | None = None
    variant: str | None = None
    meta: dict = Field(default_factory=dict)


class EventsIn(BaseModel):
    session: str
    events: list[EventIn]


@router.post("/events")
def post_events(body: EventsIn, request: Request, db: Session = Depends(get_db)):
    """Ta emot vad som hände. Aldrig mer än ett samlat knippe åt gången, och aldrig något okänt.

    Namnen är en sluten lista med flit. En öppen lista blir på ett halvår till tvåhundra namn där fem betyder
    samma sak, och då går ingen fråga att ställa till den.
    """
    if not body.session or len(body.session) > 64:
        raise HTTPException(400, "Ogiltig sessionsnyckel")
    uid = None
    auth = request.headers.get("authorization") or ""
    if auth.lower().startswith("bearer "):
        try:                                   # inloggad om det går, anonym annars: en händelse kräver ingen inloggning
            import jwt

            from .config import settings
            uid = jwt.decode(auth[7:], settings.secret_key, algorithms=["HS256"]).get("sub")
        except Exception:
            uid = None
    n = 0
    for e in body.events[:MAX_EVENTS]:
        if e.name not in EVENT_NAMES:
            continue
        db.add(Event(user_id=uid, session=body.session, name=e.name, path=e.path[:255],
                     x=None if e.x is None else max(0.0, min(1.0, e.x)),
                     y=None if e.y is None else max(0.0, min(1.0, e.y)),
                     target=(e.target or "")[:255], experiment=e.experiment, variant=e.variant,
                     meta=e.meta if isinstance(e.meta, dict) else {}))
        n += 1
    if uid:
        u = db.get(User, uid)
        if u is not None:
            u.last_seen_at = dt.datetime.now(dt.timezone.utc)
    db.commit()
    return {"stored": n}


@router.get("/content/{slug}")
def published(slug: str, db: Session = Depends(get_db)):
    """Den publicerade texten för en sida. Ett utkast syns aldrig här."""
    c = db.query(Content).filter(Content.slug == slug, Content.published.is_(True)).first()
    if c is None:
        raise HTTPException(404, "Sidan finns inte")
    return {"slug": c.slug, "title": c.title, "body": c.body,
            "updated_at": c.updated_at.isoformat() if c.updated_at else None}


@router.get("/me/role")
def my_role(user: User = Depends(current_user)):
    """Vad den inloggade får se. Gränssnittet visar admin-länken efter det här och inget annat."""
    return {"role": user.role or "member", "account_id": user.account_id, "email": user.email}
