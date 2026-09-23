"""Var tjänstens data faktiskt bor, och om den finns kvar efter nästa driftsättning.

Den frågan går inte att svara på genom att titta i webbgränssnittet. En tjänst som skriver sin databas till
behållarens eget filsystem ser ut precis som en som skriver till en monterad volym - ända tills den startas om,
och då är varje konto, varje projekt och varje uppladdad ritning borta utan ett felmeddelande någonstans. Det
är det mest förvirrande sätt en driftsättning kan gå fel på, för ingenting *kraschar*.

Så tjänsten säger det själv, utan inloggning och utan att lämna ut någon referens: vilken sorts databas den
använder, var filerna ligger, om det ligger på en egen monterad enhet, och hur många rader den faktiskt har.
`persistent` är slutsatsen av det, och `why` är skälet i klartext.

Ingen användare, inget lösenord och ingen anslutningssträng lämnar den här modulen. En URL kan bära en
referens i sig, så bara dess sort, värd och databasnamn läses av - aldrig det som står före @.
"""
from __future__ import annotations

import os

from .config import settings


def _dev(path: str) -> int | None:
    """Vilken enhet en sökväg ligger på. En monterad volym är en annan enhet än behållarens rot."""
    p = os.path.abspath(path)
    while p and not os.path.exists(p):
        parent = os.path.dirname(p)
        if parent == p:
            return None
        p = parent
    try:
        return os.stat(p).st_dev
    except OSError:
        return None


def _on_its_own_mount(path: str) -> bool | None:
    d, root = _dev(path), _dev("/")
    if d is None or root is None:
        return None
    return d != root


def database_facts() -> dict:
    """Databasens sort och plats, aldrig dess referens."""
    url = settings.database_url
    scheme = url.split("://", 1)[0]
    kind = "sqlite" if scheme.startswith("sqlite") else scheme.split("+", 1)[0]
    out: dict = {"kind": kind}
    if kind == "sqlite":
        path = url.split("://", 1)[1].lstrip("/")
        path = "/" + path if url.startswith("sqlite:////") else os.path.abspath(path)
        out["file"] = path
        out["exists"] = os.path.exists(path)
        out["bytes"] = os.path.getsize(path) if os.path.exists(path) else 0
        out["on_its_own_mount"] = _on_its_own_mount(path)
    else:
        tail = url.split("://", 1)[1]
        host = tail.split("@")[-1]                      # allt före @ är användare och lösenord: läses aldrig
        out["host"] = host.split("?")[0]
    return out


def storage_facts() -> dict:
    """Var de uppladdade ritningarna ligger, och om katalogen går att skriva i."""
    root = os.path.abspath(settings.storage_root)
    ok = None
    try:
        os.makedirs(root, exist_ok=True)
        probe = os.path.join(root, ".skrivprov")
        with open(probe, "w") as fh:
            fh.write("x")
        os.remove(probe)
        ok = True
    except OSError:
        ok = False
    n = 0
    for _dirpath, _dirs, files in os.walk(root):
        n += len(files)
        if n > 100000:
            break
    return {"root": root, "writable": ok, "files": n, "on_its_own_mount": _on_its_own_mount(root)}


def counts() -> dict:
    """Hur många rader tjänsten har. Noll rader i en tom databas och noll rader efter en tömning ser lika ut,
    men tillsammans med `persistent` går de att skilja åt."""
    from sqlalchemy import func, select

    from .db import AnalysisJob, Drawing, Project, SessionLocal, User
    out: dict = {}
    try:
        with SessionLocal() as db:
            for name, model in (("users", User), ("projects", Project), ("drawings", Drawing), ("jobs", AnalysisJob)):
                out[name] = int(db.execute(select(func.count()).select_from(model)).scalar_one())
    except Exception as e:                                      # noqa: BLE001
        out["error"] = type(e).__name__
    return out


def verdict() -> dict:
    """Allt på ett ställe, med slutsatsen först.

    En SQLite-fil i behållarens eget filsystem är inte lagring - den är ett arbetsminne som råkar se ut som en
    databas. Den som driftsätter behöver höra det i klartext innan den första ritningen laddas upp, inte efter
    nästa driftsättning.
    """
    db, st = database_facts(), storage_facts()
    if db["kind"] != "sqlite" and settings.local_installation:
        ok, why = True, f"{db['kind']} som egen tjänst; ritningarna sparas på datorns disk"
    elif db["kind"] != "sqlite":
        # The database keeps the rows, but not the drawings and the analysis results: those are files under the
        # storage root. Without a volume there they are gone after the next deployment while the rows that
        # point at them remain - a project full of drawings that cannot be opened.
        if st.get("on_its_own_mount") is True:
            ok, why = True, f"{db['kind']} som egen tjänst, ritningar och resultat på en monterad volym"
        elif st.get("on_its_own_mount") is None:
            ok, why = None, f"{db['kind']} som egen tjänst; gick inte att avgöra var ritningarna ligger"
        else:
            ok, why = False, (f"{db['kind']} som egen tjänst behåller kontona och projekten, men ritningarna och "
                              f"analysresultaten ({st.get('root')}) ligger i behållarens eget filsystem och "
                              "försvinner vid nästa driftsättning. Montera en volym på /data.")
    elif settings.local_installation:
        ok = bool(db.get("exists") and st.get("writable"))
        why = ("Lokal installation: databas och ritningar sparas på datorns disk. Säkerhetskopiera datamappen."
               if ok else "Lokal installation: kontrollera databasfilen och datamappens skrivrättigheter.")
    elif db.get("on_its_own_mount") is True and st.get("on_its_own_mount") is True:
        ok, why = True, "SQLite och filerna ligger på en monterad volym"
    elif db.get("on_its_own_mount") is None:
        ok, why = None, "gick inte att avgöra var filerna ligger"
    else:
        ok = False
        parts = []
        if db.get("on_its_own_mount") is not True:
            parts.append(f"databasen ({db.get('file')})")
        if st.get("on_its_own_mount") is not True:
            parts.append(f"ritningarna ({st.get('root')})")
        why = ("ligger i behållarens eget filsystem och försvinner vid nästa driftsättning: "
               + " och ".join(parts) + ". Montera en volym på katalogen, eller lägg till en databastjänst och "
               "peka VVS_DATABASE_URL på den.")
    from . import config as _config
    if _config.SQLITE_KEPT_OVER_PLATFORM_DATABASE:
        why += (" Obs: en databastjänst är också kopplad (DATABASE_URL), men SQLite-filen har redan data och "
                "används därför fortfarande. Flytta datan och sätt VVS_DATABASE_URL för att byta.")
    return {"persistent": ok, "why": why, "database": db, "storage": st, "rows": counts()}


def say_at_startup() -> None:
    """En rad i loggen vid uppstart. Den som söker efter sin försvunna data hittar den här."""
    v = verdict()
    mark = {True: "OK", False: "FLYKTIG", None: "OKÄND"}[v["persistent"]]
    print(f"[data] {mark}: {v['why']}", flush=True)
    print(f"[data] rader: {v['rows']}", flush=True)
