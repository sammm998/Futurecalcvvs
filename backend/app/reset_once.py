"""En engångsåterställning av tjänsten, beställd av ägaren: allt raderas och tjänsten börjar om från noll.

Tjänsten körs på en volym som ingen kan nå utom genom tjänsten själv, och ägaren bad om att alla konton,
projekt, ritningar och körningar skulle tas bort så att den kunde börja om. Det görs här, en gång: vid uppstart
jämförs RESET_ID med det som står i databasen, och står det inte där töms databasen och lagret och id:t skrivs.
Nästa uppstart ser id:t och gör ingenting. Det första kontot som skapas därefter blir administratör.

Ett nytt id här betyder en ny återställning. Det ändras bara när ägaren ber om det.
"""
import os
import shutil
from pathlib import Path

RESET_ID = "2026-10-03-owner-requested-fresh-start"
MARKER = "reset_once"


def run(storage_root: str) -> bool:
    from .db import Base, ServiceSetting, SessionLocal, engine, init_db
    init_db()
    with SessionLocal() as db:
        row = db.get(ServiceSetting, MARKER)
        if row is not None and (row.value or {}).get("v") == RESET_ID:
            return False
    # alla tabeller bort och tillbaka tomma: konton, projekt, ritningar, körningar, inställningar
    Base.metadata.drop_all(engine)
    init_db()
    root = Path(storage_root)
    if root.is_dir():
        for p in root.iterdir():
            shutil.rmtree(p, ignore_errors=True) if p.is_dir() and not p.is_symlink() else p.unlink(missing_ok=True)
    with SessionLocal() as db:
        db.add(ServiceSetting(key=MARKER, value={"v": RESET_ID}, note="Engångsåterställning beställd av ägaren"))
        db.commit()
    print(f"[reset] tjänsten återställd från noll ({RESET_ID})", flush=True)
    return True
