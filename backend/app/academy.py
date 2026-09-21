"""Akademin: var någon är, vad de klarat och vad de fått för det.

Framstegen låg i webbläsarens eget lager. Det räcker för en person som sitter vid samma dator hela tiden och
aldrig rensar något - och för ingen annan. En kollega som byter dator börjar om från noll, och adminsidans
"hur långt kommer folk" läste en tabell som ingenting någonsin skrev i.

Så framstegen ligger på kontot. Webbläsarens lager får vara kvar som reserv för den som inte loggat in, men
det är serverns svar som gäller så snart det finns ett.

Poängen räknas här och inte i gränssnittet. Ett resultat som klienten får bestämma är inte ett resultat, det
är ett önskemål - och en utmärkelse som går att sätta själv är ingen utmärkelse.
"""
from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .auth import current_user
from .db import CourseProgress, User, get_db

router = APIRouter(prefix="/api/academy", tags=["akademin"])

MAX_STEPS = 200                       # en kurs med tvåhundra steg är inte en kurs
POINTS_RIGHT = 10                     # rätt på första försöket
POINTS_EVENTUALLY = 4                 # rätt till slut


class Award:
    """En utmärkelse och vad den kräver. Villkoret prövas mot vad som står i tabellen, aldrig mot vad klienten säger."""

    def __init__(self, key: str, title: str, why: str, test):
        self.key, self.title, self.why, self.test = key, title, why, test


AWARDS = [
    Award("forsta-steget", "Första steget", "Du har gjort ett steg klart.",
          lambda p: len(p.done_steps or {}) >= 1),
    Award("halvvags", "Halvvägs", "Du har gjort minst fem steg klara i kursen.",
          lambda p: len(p.done_steps or {}) >= 5),
    Award("kursen-klar", "Kursen klar", "Alla steg i kursen är gjorda.",
          lambda p: bool(p.completed)),
    Award("utan-fel", "Utan fel", "Minst fem steg klarade på första försöket.",
          lambda p: sum(1 for s in (p.done_steps or {}).values()
                        if isinstance(s, dict) and s.get("tries") == 1 and s.get("right")) >= 5),
]


def _row(db: Session, user: User, course: str) -> CourseProgress:
    p = (db.query(CourseProgress)
         .filter(CourseProgress.user_id == user.id, CourseProgress.course == course).first())
    if p is None:
        p = CourseProgress(user_id=user.id, course=course, done_steps={}, awards={})
        db.add(p)
        db.flush()
    return p


def _score(done: dict) -> int:
    """Poängen ur stegen själva, så att den alltid stämmer med vad som står i dem."""
    total = 0
    for s in (done or {}).values():
        if not isinstance(s, dict) or not s.get("right"):
            continue
        total += POINTS_RIGHT if (s.get("tries") or 1) <= 1 else POINTS_EVENTUALLY
    return total


def _as_dict(p: CourseProgress) -> dict:
    return {"course": p.course, "step": p.step, "done_steps": p.done_steps or {},
            "completed": p.completed, "score": p.score, "awards": p.awards or {},
            "started_at": p.started_at.isoformat() if p.started_at else None,
            "updated_at": p.updated_at.isoformat() if p.updated_at else None}


@router.get("/progress")
def progress(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Allt den inloggade har gjort, per kurs."""
    rows = db.query(CourseProgress).filter(CourseProgress.user_id == user.id).all()
    return {"courses": {p.course: _as_dict(p) for p in rows},
            "awards": sorted({k for p in rows for k in (p.awards or {})}),
            "score": sum(p.score for p in rows)}


class StepIn(BaseModel):
    """Ett steg någon gjort. Klienten säger vad som hände, servern avgör vad det är värt."""
    step_id: str = Field(min_length=1, max_length=64)
    right: bool = True
    tries: int = Field(default=1, ge=1, le=99)
    step: int | None = None
    of_steps: int | None = Field(default=None, ge=1, le=MAX_STEPS)


@router.put("/progress/{course}")
def save_step(course: str, body: StepIn, user: User = Depends(current_user),
              db: Session = Depends(get_db)):
    """Skriv ned ett gjort steg, räkna om poängen och dela ut det som förtjänats.

    Ett steg som redan är gjort rätt kan inte bli ogjort av ett senare försök: den som går tillbaka och tittar
    på ett steg igen ska inte förlora det de redan klarat.
    """
    if not course or len(course) > 64:
        raise HTTPException(400, "Okänd kurs")
    p = _row(db, user, course)
    done = dict(p.done_steps or {})
    old = done.get(body.step_id) or {}
    if old.get("right") and not body.right:
        pass                                   # ett klarat steg står kvar som klarat
    else:
        done[body.step_id] = {"right": bool(body.right),
                              "tries": max(int(old.get("tries") or 0), body.tries) if old else body.tries,
                              "at": dt.datetime.now(dt.timezone.utc).isoformat()}
    p.done_steps = done
    p.step = max(p.step, body.step if body.step is not None else p.step)
    if body.of_steps:
        p.completed = sum(1 for s in done.values() if s.get("right")) >= body.of_steps
    p.score = _score(done)

    got = dict(p.awards or {})
    fresh = []
    for a in AWARDS:
        if a.key not in got and a.test(p):
            got[a.key] = dt.datetime.now(dt.timezone.utc).isoformat()
            fresh.append({"key": a.key, "title": a.title, "why": a.why})
    p.awards = got
    db.commit()
    return {**_as_dict(p), "new_awards": fresh}


@router.get("/awards")
def awards(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Alla utmärkelser som finns, och vilka av dem som är tagna. En låst utmärkelse säger vad som krävs."""
    rows = db.query(CourseProgress).filter(CourseProgress.user_id == user.id).all()
    got = {k: v for p in rows for k, v in (p.awards or {}).items()}
    return {"awards": [{"key": a.key, "title": a.title, "why": a.why,
                        "taken_at": got.get(a.key)} for a in AWARDS]}
