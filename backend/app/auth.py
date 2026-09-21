from __future__ import annotations

import datetime as dt

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
import bcrypt
from sqlalchemy.orm import Session

from .config import settings
from .db import User, get_db

oauth2 = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def hash_password(p: str) -> str:
    return bcrypt.hashpw(p.encode("utf-8")[:72], bcrypt.gensalt()).decode("ascii")


def verify_password(p: str, h: str) -> bool:
    try:
        return bcrypt.checkpw(p.encode("utf-8")[:72], h.encode("ascii"))
    except ValueError:
        return False


def create_token(user: User) -> str:
    exp = dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=settings.access_token_minutes)
    return jwt.encode({"sub": user.id, "email": user.email, "exp": exp}, settings.secret_key, algorithm="HS256")


def current_user(token: str = Depends(oauth2), db: Session = Depends(get_db)) -> User:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Ogiltig eller utgången inloggning")
    user = db.get(User, payload.get("sub"))
    if user is None:
        raise HTTPException(status_code=401, detail="Okänd användare")
    return user


def current_admin(user: User = Depends(current_user)) -> User:
    """The one gate the service side sits behind.

    Every admin route depends on this and not on a check written out inside the route, because a check written
    out inside a route is a check somebody forgets to write in the next one. A member reaching an admin route is
    told it is not theirs, not that it does not exist: pretending the page is missing only makes them ask
    support what happened to it.
    """
    if (user.role or "member") != "admin":
        raise HTTPException(status_code=403, detail="Det här är administratörens sidor")
    return user


def current_staff(user: User = Depends(current_user)) -> User:
    """A partner sees their own referrals and their own commission; an admin sees everyone's."""
    if (user.role or "member") not in ("admin", "partner"):
        raise HTTPException(status_code=403, detail="Kräver partner- eller administratörsbehörighet")
    return user

# ------------------------------------------------------------------------------------------------------------
# Att bromsa den som gissar
# ------------------------------------------------------------------------------------------------------------
# Ett lösenord på sex tecken tål inte obegränsat många försök, och utan en broms är bcrypt det enda som håller
# emot - en tiondels sekund per gissning är tiotusen gissningar på en kvart. Bromsen är i minnet med flit: den
# ska inte kosta en skrivning per felslag i lagret, och att den nollas vid omstart är ett pris utan betydelse.
# Räknas per adress OCH per avsändare, så att en gissare inte kan låsa ute ett konto genom att slå fel på det,
# och inte heller sprida sina gissningar över många konton från en och samma plats.
import threading as _threading
import time as _time
from collections import defaultdict as _dd

LOGIN_WINDOW_S = 900              # femton minuter
LOGIN_MAX_FAILS = 10              # per adress, per fönster
LOGIN_MAX_FAILS_IP = 60           # per avsändare, per fönster: många konton från ett håll
_fails: dict = _dd(list)
_fails_lock = _threading.Lock()

# Samma tid för en adress som inte finns som för en som finns med fel lösenord. Utan det svarar den okända
# adressen på en millisekund och den kända på hundra, och tiden säger vilka konton som finns.
_DUMMY_HASH = hash_password("aldrig-ett-riktigt-losenord")


def _prune(key: str, now: float) -> list:
    xs = [t for t in _fails[key] if now - t < LOGIN_WINDOW_S]
    _fails[key] = xs
    return xs


def login_blocked(email: str, ip: str) -> int:
    """Sekunder kvar av spärren, eller noll."""
    now = _time.time()
    with _fails_lock:
        for key, cap in ((f"e:{email}", LOGIN_MAX_FAILS), (f"ip:{ip}", LOGIN_MAX_FAILS_IP)):
            xs = _prune(key, now)
            if len(xs) >= cap:
                return int(LOGIN_WINDOW_S - (now - xs[0])) + 1
    return 0


def login_failed(email: str, ip: str) -> None:
    now = _time.time()
    with _fails_lock:
        _fails[f"e:{email}"].append(now)
        _fails[f"ip:{ip}"].append(now)


def login_succeeded(email: str) -> None:
    with _fails_lock:
        _fails.pop(f"e:{email}", None)


def verify_or_burn(password: str, stored_hash: str | None) -> bool:
    """Pröva lösenordet, och bränn lika lång tid när det inte finns något att pröva mot."""
    if stored_hash is None:
        verify_password(password, _DUMMY_HASH)
        return False
    return verify_password(password, stored_hash)
