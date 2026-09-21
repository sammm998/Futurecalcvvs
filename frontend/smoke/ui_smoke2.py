"""The pages the first smoke never reached: the project analysis, the admin, the academy drills.

Same idea as ui_smoke.py - click everything with the console open and report what it said - on the parts of the
application that were built after that script was written. Run against serve_seeded.py on 127.0.0.1:8077.

The seeded user is made admin here, straight in the database, because that is the only way to be one: the role
comes from the server and never from anything the browser can say.
"""
import asyncio, os, sys
from playwright.async_api import async_playwright
SP = os.environ.get("SP", os.path.dirname(os.path.abspath(__file__)))
job, tok = open(f"{SP}/ui/job.txt").read().split()
BASE = "http://127.0.0.1:8077"
errs: list[str] = []
found: list[str] = []


def note(label):
    if errs:
        found.append(f"{label}: {errs[-1][:220]}")
        print(f"  !! {label}: {errs[-1][:220]}")
        errs.clear()


async def click_all(pg, sel, label, limit=30):
    n = await pg.locator(sel).count()
    for i in range(min(n, limit)):
        el = pg.locator(sel).nth(i)
        try:
            if not await el.is_visible():
                continue
            t = (await el.inner_text())[:28].replace("\n", " ")
            await el.click(timeout=2500)
            await pg.wait_for_timeout(320)
            note(f"{label} «{t}»")
        except Exception as e:
            print(f"  (kunde inte klicka {label} #{i}: {str(e)[:70]})")


async def main():
    async with async_playwright() as p:
        exe = os.environ.get("CHROME") or "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
        b = await p.chromium.launch(executable_path=exe if os.path.exists(exe) else None)
        ctx = await b.new_context(viewport={"width": 1500, "height": 940})
        pg = await ctx.new_page()
        pg.on("pageerror", lambda e: errs.append(f"pageerror: {e}"))
        pg.on("console", lambda m: errs.append(f"console.error: {m.text}") if m.type == "error" else None)
        # ett anrop som svarar med fel är också ett fynd, även när sidan i sig inte kraschar
        pg.on("response", lambda r: errs.append(f"http {r.status} {r.url.split('8077')[-1]}")
              if r.status >= 400 and "/api/" in r.url else None)

        # rollen kommer från servern och aldrig från webbläsaren, så den sätts där den bor: i lagret
        import glob, sqlite3
        dbs = sorted(glob.glob("/tmp/ui-*/ui.db"), key=os.path.getmtime)
        assert dbs, "hittar inte den seedade tjänstens lager"
        cx = sqlite3.connect(dbs[-1]); cx.execute("UPDATE users SET role='admin'"); cx.commit(); cx.close()

        await pg.goto(f"{BASE}/login", wait_until="networkidle")
        await pg.evaluate(f"localStorage.setItem('vvs_token', '{tok}')")

        print("== projektet: knappen till projektanalysen ==")
        await pg.goto(f"{BASE}/projekt", wait_until="networkidle"); await pg.wait_for_timeout(800)
        await pg.locator("a.ttl, .item a").first.click(); await pg.wait_for_timeout(900)
        note("öppna projektet")
        pid = pg.url.rstrip("/").split("/")[-1]
        await pg.get_by_role("button", name="Analysera projektet").click(); await pg.wait_for_timeout(900)
        note("till projektanalysen")
        assert pg.url.endswith("/analys"), pg.url

        print("== projektanalysen: valet, läsningen, flikarna, en rättelse ==")
        # andra körningen mot samma tjänst: valet är redan gjort och knappen finns inte - det är rätt beteende
        pick = pg.get_by_role("button", name="Välj projektanalys")
        if await pick.count():
            await pick.click(); await pg.wait_for_timeout(1000)
            note("välj projektanalys")
        # "Läs handlingen" första gången, "Läs om" sedan: samma knapp, olika ord
        await pg.locator(".head .row button").first.click()
        for _ in range(60):
            await pg.wait_for_timeout(500)
            if await pg.locator(".tabs button", has_text="Handlingar").count():
                break
        note("läs handlingen")
        await click_all(pg, ".tabs button", "pa-flik")
        await pg.locator(".tabs button", has_text="Handlingar").click(); await pg.wait_for_timeout(500)
        fix = pg.get_by_role("button", name="Rätta", exact=True)
        if await fix.count():
            await fix.first.click(); await pg.wait_for_timeout(400)
            await pg.locator(".pa-fix select").select_option("building")
            await pg.locator(".pa-fix input").first.fill("B")
            await pg.locator(".pa-fix button", has_text="Rätta").click(); await pg.wait_for_timeout(900)
            note("rätta huset")
            stale = await pg.locator(".pa-stale").count()
            print(f"  rättelse sparad · bannern 'läs om' visas: {bool(stale)}")
            if stale:
                await pg.locator(".pa-stale button").click()
                # bannern försvinner i samma ögonblick som omläsningen STARTAR - att vänta på den är att läsa
                # sidan innan svaret kommit. Vänta på det som faktiskt betyder klar: trädet ritas om med huset.
                for _ in range(80):
                    await pg.wait_for_timeout(500)
                    if "Hus B" in await pg.inner_text("body"):
                        break
                note("läs om efter rättelse")
                body = await pg.inner_text("body")
                print(f"  efter omläsning: hus B i trädet: {'Hus B' in body}")
                if "Hus B" not in body:
                    found.append("rättelsen till hus B syns inte i trädet efter omläsning")
        else:
            print("  (ingen Rätta-knapp: inga blad med id?)")
        await pg.locator(".tabs button", has_text="Före / efter").click(); await pg.wait_for_timeout(500)
        note("före/efter-fliken")
        await pg.locator(".tabs button", has_text="Mängder").click(); await pg.wait_for_timeout(500)
        note("mängder-fliken")
        # tabellhuvuden är versala via CSS, och innerText följer CSS: jämför utan skiftläge
        body = (await pg.inner_text("body")).lower()
        print(f"  mängder per hus visas: {'horisontellt' in body}")
        if "horisontellt" not in body:
            found.append("mängdfliken visar inga mängder trots två färdiga läsningar")

        print("== projektagenten: en färdig fråga utan modell ==")
        await pg.locator(".tabs button", has_text="Agent").click(); await pg.wait_for_timeout(500)
        await pg.get_by_role("button", name="Vad består handlingen av?").click()
        for _ in range(40):
            await pg.wait_for_timeout(400)
            if await pg.locator(".agentchat .msg.agent").count():
                break
        note("projektagenten")
        ans = (await pg.locator(".agentchat .msg.agent").last.inner_text()) if await pg.locator(".agentchat .msg.agent").count() else ""
        # svaret på "vad består handlingen av" bär husen och totalen; bladen listas bara om något är oläst
        ok = ("hus" in ans) and ("totalt" in ans or "documents" in ans)
        print(f"  svar med hus och total: {ok}")
        if not ok:
            found.append("projektagentens svar saknar hus och total")

        print("== markera: en längd ritad och sparad på ritningen ==")
        await pg.goto(f"{BASE}/jobs/{job}", wait_until="networkidle"); await pg.wait_for_timeout(5000)
        await pg.locator(".tabs button", has_text="Markera").click(); await pg.wait_for_timeout(600)
        note("markera-fliken")
        await pg.get_by_role("button", name="Längd", exact=True).click(); await pg.wait_for_timeout(300)
        box = await pg.locator(".viewer .page").bounding_box()
        x, y = box["x"] + 260, box["y"] + 300
        await pg.mouse.click(x, y); await pg.wait_for_timeout(200)
        await pg.mouse.click(x + 120, y); await pg.wait_for_timeout(200)
        await pg.mouse.dblclick(x + 120, y + 80); await pg.wait_for_timeout(600)
        note("rita längd")
        save = pg.get_by_role("button", name="Spara markering")
        print(f"  utkast att spara: {await save.count() > 0}")
        if await save.count():
            await save.first.click(); await pg.wait_for_timeout(1500)
            note("spara markering")
            rows = await pg.locator(".corr table tbody tr").count()
            body = await pg.inner_text("body")
            print(f"  rader i listan: {rows} · mått i meter: {' m' in body}")
            if rows < 1:
                found.append("markeringen sparades inte i listan")
        else:
            found.append("ingen markering att spara efter ritandet")

        print("== kalkyl: knappen, sidan, räkna, spara, anbud ==")
        cta = pg.locator(".tabs .tabs-cta")
        print(f"  kalkylera-knappen i flikraden: {await cta.count() > 0}")
        if not await cta.count():
            found.append("ingen Kalkylera-knapp i analysens flikrad")
        else:
            await cta.first.click(); await pg.wait_for_timeout(1500)
            note("kalkylera-knappen")
        on_page = "/kalkyl" in pg.url and await pg.locator(".calcpage").count() > 0
        print(f"  egen kalkylsida: {on_page}")
        if not on_page:
            found.append("Kalkylera-knappen ledde inte till kalkylsidan")
        calc_btn = pg.locator(".calc-actions button", has_text="Kalkylera")
        if not await calc_btn.count():
            calc_btn = pg.locator(".calc-actions button", has_text="Räkna om")
        await calc_btn.first.click()
        for _ in range(40):
            await pg.wait_for_timeout(400)
            if await pg.locator(".calc-stats .adm-stat").count():
                break
        note("kalkylera")
        body = (await pg.inner_text("body")).lower()
        print(f"  summa visas: {'anbudssumma' in body} · rader: {await pg.locator('.calc-table tbody tr').count()}")
        if "anbudssumma" not in body:
            found.append("kalkylen visar ingen anbudssumma")
        await pg.locator(".calc-actions button", has_text="Spara kalkyl").click(); await pg.wait_for_timeout(1500)
        note("spara kalkyl")
        pv = pg.locator(".calc-anbud button", has_text="Förhandsgranska")
        print(f"  anbudsknappar efter spar: {await pv.count() > 0}")
        if await pv.count():
            await pv.first.click()
            for _ in range(40):
                await pg.wait_for_timeout(500)
                if await pg.locator("img.anbud-page").count():
                    break
            note("förhandsgranska anbud")
            n_img = await pg.locator("img.anbud-page").count()
            loaded = n_img > 0 and await pg.locator("img.anbud-page").first.evaluate("el => el.complete && el.naturalWidth > 200")
            print(f"  anbudets sidor i förhandsgranskningen: {n_img} · bilden laddad: {loaded}")
            if not loaded:
                found.append("anbudets förhandsgranskning visar inga sidor")
        else:
            found.append("anbudsknapparna syns inte efter spar")

        print("== akademin: övningarna och framstegen på kontot ==")
        await pg.goto(f"{BASE}/lar", wait_until="networkidle"); await pg.wait_for_timeout(900)
        note("akademin")
        cur = await pg.locator(".lf-current").count()
        locked = await pg.locator(".lf-railitem.locked").count()
        print(f"  pågående kurs visas: {bool(cur)} · låsta kurser i listan: {locked}")
        if not cur:
            found.append("ingen pågående kurs visas i akademin")
        # en låst kurs går att öppna ändå: välj den i kurslistan och tryck
        if locked:
            await pg.locator(".lf-railitem.locked").first.click(); await pg.wait_for_timeout(300)
            note("välj låst kurs")
            opn = pg.locator(".lf-lock button", has_text="Öppna ändå")
            if await opn.count():
                await opn.first.click(); await pg.wait_for_timeout(300)
                note("öppna låst kurs ändå")
            else:
                found.append("en låst kurs gick inte att öppna ändå")
        await pg.locator(".lf-nav button", has_text="Öva").click(); await pg.wait_for_timeout(500)
        note("öva-fliken")
        n = await pg.locator(".lf-drills .lx").count()
        print(f"  {n} övningar synliga")
        if not n:
            found.append("inga övningar under Öva")
        await click_all(pg, ".lf-drills button", "övningsknapp", limit=25)
        await pg.locator(".lf-nav button", has_text="Utmärkelser").click(); await pg.wait_for_timeout(500)
        note("utmärkelser")
        print(f"  utmärkelser synliga: {await pg.locator('.lf-award').count()}")
        await pg.locator(".lf-nav button", has_text="Kurser").click(); await pg.wait_for_timeout(400)
        # ett steg i guiden, och sedan en omladdning: framsteget ska komma från kontot, inte bara från lagret
        # knappen heter olika beroende på hur långt man kommit; det är hjältens första knapp oavsett text
        await pg.locator(".lf-hero .row button").first.click(); await pg.wait_for_timeout(700)
        opt = pg.locator(".wz-quiz-opts button").first
        if await opt.count():
            await opt.click(); await pg.wait_for_timeout(200)
        # ett steg framåt om guiden har ett; på sista steget heter knappen "Klart" - alla 22 stegen täcks av
        # det första rökprovet, det här ska bara lämna ett spår på kontot
        nxt = pg.locator(".wz-foot button", has_text="Nästa")
        if await nxt.count():
            await nxt.first.click(); await pg.wait_for_timeout(500)
        else:
            klar = pg.locator(".wz-foot button", has_text="Klart")
            if await klar.count():
                await klar.first.click(); await pg.wait_for_timeout(500)
        await pg.keyboard.press("Escape"); await pg.wait_for_timeout(500)
        note("ett steg i guiden")
        await pg.evaluate("localStorage.removeItem('vvs.learn')")     # glöm det lokala: bara kontot är kvar
        await pg.goto(f"{BASE}/lar", wait_until="networkidle"); await pg.wait_for_timeout(1200)
        ring = await pg.locator(".lf-ring span").inner_text()
        print(f"  framsteg efter att det lokala lagret rensats: {ring.strip().replace(chr(10), '')}")
        note("framsteg från kontot")

        print("== admin: varje flik och varje knapp ==")
        await pg.goto(f"{BASE}/admin", wait_until="networkidle"); await pg.wait_for_timeout(1000)
        note("admin")
        tabs = await pg.locator(".adm-nav button").count()
        print(f"  {tabs} flikar")
        for i in range(tabs):
            t = pg.locator(".adm-nav button").nth(i)
            name = (await t.inner_text()).strip()
            await t.click(); await pg.wait_for_timeout(700)
            note(f"admin-flik {name}")
            # varje knapp som inte är destruktiv på fliken
            btns = pg.locator("main button:not(.adm-nav button)")
            m = await btns.count()
            for k in range(min(m, 12)):
                bt = btns.nth(k)
                try:
                    if not await bt.is_visible():
                        continue
                    label = (await bt.inner_text()).strip()[:24]
                    if any(w in label.lower() for w in ("ta bort", "radera", "makulera")):
                        continue
                    await bt.click(timeout=2000); await pg.wait_for_timeout(350)
                    note(f"admin {name} «{label}»")
                    # stäng en eventuell dialog/prompt-rest
                    await pg.keyboard.press("Escape")
                except Exception:
                    pass
        # partnerformuläret hela vägen: ny partner, spara, betala ut
        await pg.locator(".adm-nav button", has_text="Partners").click(); await pg.wait_for_timeout(600)
        np_ = pg.get_by_role("button", name="Ny partner")
        if await np_.count():
            await np_.click(); await pg.wait_for_timeout(300)
            fields = pg.locator(".adm-form input")
            await fields.nth(0).fill("Anna Rök"); await fields.nth(1).fill("anna@rok.se")
            await pg.locator(".adm-form input[placeholder='ANNA10']").fill("ANNA10")
            await pg.get_by_role("button", name="Spara", exact=True).click(); await pg.wait_for_timeout(900)
            note("spara partner")
            body = await pg.inner_text("body")
            print(f"  partnern syns i listan: {'Anna Rök' in body}")

        print(f"\nSIDAN LEVER: {len((await pg.inner_text('body')).strip()) > 200}")
        print(f"FYND: {len(found)}")
        for f in found:
            print("  -", f)
        await b.close()
        sys.exit(1 if found else 0)
asyncio.run(main())
