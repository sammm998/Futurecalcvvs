"""Lägg t() runt varje synlig sträng i gränssnittet, och räkna det som återstår.

Gränssnittet är skrivet på svenska och svenskan är översättningsnyckeln (frontend/src/i18n.ts). För att en
sträng ska gå att läsa på engelska måste den gå genom t(). Det här verktyget gör den mekaniska delen: det
hittar texten mellan taggar och i de attribut som visas för en läsare, och lägger t() runt den.

Vad det aldrig rör: klassnamn, id, url:er, api-vägar, nycklar, värden - allt som är kod och inte text. Det
avgörs av vilka attribut som läses (title, placeholder, aria-label, alt, label) och av att texten mellan taggar
varken får innehålla klammer, taggar eller radbrytning.

    python3 frontend/tools/i18n_wrap.py --report          vad som återstår, fil för fil
    python3 frontend/tools/i18n_wrap.py --areas           ordbokens delar och vad som återstår i varje
    python3 frontend/tools/i18n_wrap.py --keys            varje nyckel som saknar engelsk rad
    python3 frontend/tools/i18n_wrap.py --keys admin      ...bara de som hör till en del
    python3 frontend/tools/i18n_wrap.py --rename          döp om den importerade bindningen till tr
    python3 frontend/tools/i18n_wrap.py src/pages/X.tsx   skriv om en fil (eller flera)

Bindningen heter `tr`, inte `t`. Skälet är mätt: `t` är ett vanligt lokalt namn i den här koden - en
tidtagare, en interpolationsfaktor, ett tillstånd - och i 44 filer finns ett lokalt `t`. Där ett sådant
ligger i samma räckvidd som ett inlagt anrop pekar anropet på det lokala namnet i stället för på ordboken,
och det syns inte i tsc när det lokala värdet är `any`: det kraschar först i webbläsaren. Ett namn som
ingen annan använder gör felet omöjligt i stället för osannolikt.
"""
from __future__ import annotations

import os
import re
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
SRC = os.path.join(ROOT, "src")
BIND = "tr"                                       # namnet den importerade funktionen har i koden
PROPS = ("title", "placeholder", "aria-label", "alt", "label")
# filer som inte är gränssnitt: ordboken själv, ritmotorn, testfixturer
SKIP = ("/i18n/", ".test.", ".fixture.", "/cad/geom", "vite-env")

TEXT = re.compile(r'([^=!<>+\-*/%&|,])(>)([^<>{}\n]+)(<[A-Za-z/])')
# JS-uttryck ser ut som JSX-text för ett reguljärt uttryck: `{m > 0 ? a : <span>` har ett `>`, text, och ett `<`.
# Skillnaden är att texten då bär operatorer. Bär den någon av de här är den kod, och lämnas i fred.
CODE_CHARS = set("?:()[]=;&|")
PROP = re.compile(r'\b(' + "|".join(p.replace("-", r"\-") for p in PROPS) + r')="([^"\n]+)"')
WORDY = re.compile(r"[A-Za-zÅÄÖåäö]{2,}")
CODEISH = re.compile(r"^[\w.\-/#]+$")            # ett enda ord utan mellanslag: oftast kod, inte text


def wordy(s: str) -> bool:
    s = s.strip()
    if not s or not WORDY.search(s):
        return False
    if CODEISH.match(s) and " " not in s and not re.search(r"[åäöÅÄÖ]", s):
        return False                              # DN, px, id-liknande: lämna
    return True


def wrap(src: str) -> tuple[str, int]:
    n = 0

    def t_text(m):
        nonlocal n
        raw = m.group(3)
        s = raw.strip()
        if not wordy(s) or '"' in s or set(s) & CODE_CHARS:
            return m.group(0)
        n += 1
        lead = raw[: len(raw) - len(raw.lstrip())]
        tail = raw[len(raw.rstrip()):]
        return f'{m.group(1)}{m.group(2)}{lead}{{{BIND}("{s}")}}{tail}{m.group(4)}'

    def t_prop(m):
        nonlocal n
        s = m.group(2).strip()
        if not wordy(s) or '"' in s or "<" in s or ">" in s:
            return m.group(0)
        n += 1
        return f'{m.group(1)}={{{BIND}("{s}")}}'

    src = TEXT.sub(t_text, src)
    src = PROP.sub(t_prop, src)
    return src, n


def ensure_import(src: str, path: str) -> str:
    if re.search(r'from "[^"]*i18n"', src):
        return src
    depth = os.path.relpath(SRC, os.path.dirname(path)).replace("\\", "/")
    rel = "./i18n" if depth == "." else f"{depth}/i18n"
    m = re.search(r'^import .*?;\s*$', src, re.M)
    line = f'import {{ t as {BIND} }} from "{rel}";'
    if m:
        return src[: m.end()] + "\n" + line + src[m.end():]
    return line + "\n" + src


def files() -> list[str]:
    out = []
    for dp, dirs, fs in os.walk(SRC):
        dirs[:] = [d for d in dirs if d != "node_modules"]
        for f in sorted(fs):
            p = os.path.join(dp, f)
            if f.endswith(".tsx") and not any(s in p.replace("\\", "/") for s in SKIP):
                out.append(p)
    return out


# Ordboken ligger i delar, en per område, och en nyckel hör till det första område vars filer använder den.
# Ordningen är därför inte alfabetisk utan den ordning ett område ska översättas i: ramen först, för header,
# meny och inloggning syns på varje sida, och sedan det publika, som är det en engelsktalande besökare ser
# innan hon loggat in.
AREAS: list[tuple[str, tuple[str, ...]]] = [
    ("ram",       ("src/App.tsx", "src/components/SiteHeader", "src/components/Boundary", "src/components/PublicFrame",
                   "src/components/Status", "src/fc/Nav", "src/pages/Login", "src/pages/Register")),
    ("publikt",   ("src/fc/", "src/pages/Landing", "src/pages/HowItWorks", "src/pages/Pricing", "src/pages/About",
                   "src/pages/Contact", "src/pages/Docs", "src/pages/Architecture", "src/pages/Feature",
                   "src/pages/Education", "src/pages/LearnPage", "src/components/Landing", "src/components/Feature",
                   "src/components/AgentShowcase", "src/components/AcademySection", "src/components/Evidence",
                   "src/components/StyleFan", "src/components/LayerStack", "src/components/Tilted",
                   "src/components/Reveal", "src/components/ChapterBar", "src/components/PageCurtain")),
    ("mangd",     ("src/components/QuantityTable", "src/components/PdfViewer", "src/components/LegendView",
                   "src/components/Corrections", "src/components/Markups", "src/components/Reasoning",
                   "src/components/Analysis", "src/components/Drawing3D", "src/components/DrawingTo3D",
                   "src/components/DrawingUpload", "src/pages/Analysis", "src/pages/Takeoff")),
    ("projekt",   ("src/pages/Project", "src/pages/Drawing", "src/pages/Calc", "src/pages/Material",
                   "src/pages/Credits", "src/pages/Agent", "src/components/ProjectAgentChat",
                   "src/components/AgentChat")),
    ("admin",     ("src/pages/Admin", "src/components/Admin")),
    ("cad",       ("src/pages/Cad", "src/pages/BuildingCad", "src/cad/", "src/components/BuildingView3D")),
    ("akademi",   ("src/academy/", "src/components/Academy", "src/components/Learn", "src/components/Lecture")),
    ("innehall",  ("src/learn.ts", "src/features.ts", "src/agents.ts", "src/frontier.ts", "src/legend.ts")),
    ("server",    ("src/api.ts",)),
]
OVRIGT = "ovrigt"                                 # allt som inte pekats ut: ska vara tomt, och syns om det inte är det


def area_of(path: str) -> str:
    rp = os.path.relpath(path, ROOT).replace("\\", "/")
    for name, heads in AREAS:
        if any(rp.startswith(h) for h in heads):
            return name
    return OVRIGT


IMPORT = re.compile(r'import\s*\{([^}]*)\}\s*from\s*"([^"]*\bi18n)"')
CALL = re.compile(r'(?<![\w$.])t\("')


def rename_one(src: str) -> tuple[str, int]:
    """Byt den importerade `t` mot `tr` i en fil, och varje anrop som hörde till den.

    Ett anrop skrivs om bara i en fil som faktiskt importerar den bara `t`:n. Ligger där ett lokalt `t` i
    vägen är det just de anropen som pekar fel i dag, och de ska med. Ett `t(` som redan är egendom av något
    annat (`x.t(`, `setT(`) rörs inte - därför den negativa blicken bakåt.
    """
    m = IMPORT.search(src)
    if not m:
        return src, 0
    names = [n.strip() for n in m.group(1).split(",") if n.strip()]
    if "t" not in names:
        return src, 0
    fixed = ", ".join("t as " + BIND if n == "t" else n for n in names)
    src = src[: m.start()] + f'import {{ {fixed} }} from "{m.group(2)}"' + src[m.end():]
    src, n = CALL.subn(BIND + '("', src)
    return src, n


def rename() -> None:
    total = 0
    for p in every_file():
        src = open(p, encoding="utf-8").read()
        out, n = rename_one(src)
        if out != src:
            open(p, "w", encoding="utf-8").write(out)
            total += n
            print(f"{n:5d}  {os.path.relpath(p, ROOT)}")
    print(f"\nsumma: {total} anrop döpta till {BIND}()")


def every_file() -> list[str]:
    """Varje modul under src, inte bara .tsx: ordboken talar också i .ts-filer."""
    out = []
    for dp, dirs, fs in os.walk(SRC):
        dirs[:] = [d for d in dirs if d != "node_modules"]
        for f in sorted(fs):
            p = os.path.join(dp, f)
            if f.endswith((".ts", ".tsx")) and "/i18n/" not in p.replace("\\", "/"):
                out.append(p)
    return out


def keys_in(src: str) -> set[str]:
    # trf() bär sina tal efter nyckeln, så avslutningen är antingen parentesen eller kommat före första talet
    return set(re.findall(r'(?<![\w$.])(?:t|tr|trf)\("((?:[^"\\]|\\.)*)"\s*[,)]', src))


def dictionary() -> set[str]:
    """Varje nyckel som har en engelsk rad, ur ordbokens alla delar."""
    have: set[str] = set()
    d = os.path.join(SRC, "i18n", "en")
    for f in sorted(os.listdir(d)):
        if f.endswith(".ts"):
            have |= set(re.findall(r'\n  "((?:[^"\\]|\\.)*)":',
                                   open(os.path.join(d, f), encoding="utf-8").read()))
    return have


def report(only: str = "") -> None:
    """Vad som återstår, fil för fil - och i summan som unika nycklar, inte som en summa per fil.

    Skillnaden är inte kosmetisk: samma sträng står på tio sidor, och en summa per fil räknar den tio gånger.
    Det talet går inte att jämföra med antalet rader i ordboken, och det är just den jämförelsen man vill göra.
    """
    have = dictionary()
    rows, alla, saknade = [], set(), set()
    for p in files():
        if only and area_of(p) != only:
            continue
        src = open(p, encoding="utf-8").read()
        ks = keys_in(src)
        _, n = wrap(src)
        alla |= ks
        miss = {k for k in ks if k not in have}
        saknade |= miss
        if n or miss:
            rows.append((n, len(miss), len(ks), os.path.relpath(p, ROOT)))
    rows.sort(reverse=True)
    print(f"{'oomslutna':>10} {'utan engelska':>14} {'nycklar':>8}  fil")
    for n, miss, ks, p in rows[:40]:
        print(f"{n:10d} {miss:14d} {ks:8d}  {p}")
    print(f"\nsumma: {sum(r[0] for r in rows)} strängar utan t(), {len(saknade)} unika nycklar utan engelsk rad, "
          f"{len(alla)} unika nycklar" + (f" i {only}" if only else ""))


def areas_report() -> None:
    """Ordbokens delar, i den ordning de ska översättas, med det som återstår i varje."""
    have = dictionary()
    per: dict[str, set[str]] = {}
    for p in every_file():
        ks = keys_in(open(p, encoding="utf-8").read())
        if ks:
            per.setdefault(area_of(p), set()).update(ks)
    seen: set[str] = set()
    print(f"{'del':10} {'egna':>7} {'utan engelska':>14}")
    for name, _ in AREAS + [(OVRIGT, ())]:
        own = per.get(name, set()) - seen
        seen |= per.get(name, set())
        print(f"{name:10} {len(own):7d} {len(own - have):14d}")
    print(f"{'summa':10} {len(seen):7d} {len(seen - have):14d}")


def main(argv: list[str]) -> None:
    if "--rename" in argv:
        return rename()
    if "--areas" in argv:
        return areas_report()
    named = [a for a in argv if not a.startswith("--")]
    only = named[0] if named and named[0] in {n for n, _ in AREAS} else ""
    if "--report" in argv:
        return report(only)
    if "--keys" in argv:
        have = dictionary()
        seen: set[str] = set()
        for p in every_file():
            if only and area_of(p) != only:
                continue
            seen |= keys_in(open(p, encoding="utf-8").read())
        for k in sorted(seen - have):
            print(k)
        return
    targets = [a for a in argv if not a.startswith("--")]
    for rel in targets:
        p = rel if os.path.isabs(rel) else os.path.join(ROOT, rel)
        src = open(p, encoding="utf-8").read()
        out, n = wrap(src)
        if n:
            out = ensure_import(out, p)
            open(p, "w", encoding="utf-8").write(out)
        print(f"{n:5d}  {os.path.relpath(p, ROOT)}")


if __name__ == "__main__":
    main(sys.argv[1:])
