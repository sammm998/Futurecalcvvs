"""Click through the whole application with the console open.

A type check finds what does not compile. It does not find a handler that reads an event after the event is
over - which is what took the whole page down the first time somebody drew a pipe. This walks the landing page,
the sign-in, the project list, every step of the academy, every tab and control of a reading, and every
correction mode, and reports anything the console says.

    python frontend/smoke/serve_seeded.py     # in one shell: the real service, seeded, on 127.0.0.1:8077
    python frontend/smoke/ui_smoke.py         # in another: clicks through it

The script is deliberately dumb: it clicks everything it can see and prints what broke. Two real bugs came out
of it - a click handler that read its event after the event was over, and a frame that took the pointer on the
way down so a run could never be picked by clicking it.
"""
import asyncio, re, os
from playwright.async_api import async_playwright
SP = os.environ.get("SP", os.path.dirname(os.path.abspath(__file__)))
job, tok = open(f"{SP}/ui/job.txt").read().split()
BASE = "http://127.0.0.1:8077"
errs: list[str] = []

async def click_all(pg, sel, label, limit=40):
    n = await pg.locator(sel).count()
    for i in range(min(n, limit)):
        el = pg.locator(sel).nth(i)
        try:
            if not await el.is_visible():
                continue
            t = (await el.inner_text())[:30].replace("\n", " ")
            await el.click(timeout=2500)
            await pg.wait_for_timeout(280)
            if errs:
                print(f"  !! efter {label} «{t}»: {errs[-1][:200]}")
                errs.clear()
        except Exception as e:
            print(f"  (kunde inte klicka {label} #{i}: {str(e)[:70]})")

async def main():
    async with async_playwright() as p:
        # sökvägen till webbläsaren skiljer sig mellan maskiner; CHROME i miljön vinner, annars Playwrights egen
        exe = os.environ.get("CHROME") or "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
        b = await p.chromium.launch(executable_path=exe if os.path.exists(exe) else None)
        ctx = await b.new_context(viewport={"width": 1500, "height": 940})
        pg = await ctx.new_page()
        pg.on("pageerror", lambda e: errs.append(f"pageerror: {e}"))
        pg.on("console", lambda m: errs.append(f"console.error: {m.text}") if m.type == "error" else None)

        print("== landning ==")
        await pg.goto(f"{BASE}/", wait_until="networkidle"); await pg.wait_for_timeout(1500)
        await pg.evaluate("window.scrollTo(0, document.body.scrollHeight)"); await pg.wait_for_timeout(2000)
        print("  ", errs[-2:] or "rent")
        errs.clear()

        print("== inloggning + projekt ==")
        await pg.goto(f"{BASE}/login", wait_until="networkidle")
        await pg.evaluate(f"localStorage.setItem('vvs_token', '{tok}')")
        await pg.goto(f"{BASE}/projekt", wait_until="networkidle"); await pg.wait_for_timeout(1200)
        print("  ", errs[-2:] or "rent"); errs.clear()

        print("== akademin: alla steg ==")
        await pg.goto(f"{BASE}/lar", wait_until="networkidle"); await pg.wait_for_timeout(700)
        # knappen heter olika beroende på hur långt kontot kommit: ett annat rökprov kan ha hunnit före
        await pg.get_by_role("button", name=re.compile("Starta guiden|Fortsätt guiden|Gå igenom igen")).click(); await pg.wait_for_timeout(700)
        # every step of the course, however many the course has grown to - a fixed count silently stops testing
        # the steps added after it was written
        head = await pg.locator(".wz-kicker").inner_text()
        n = int(head.upper().rsplit(" AV ", 1)[-1])   # css uppercases the kicker, the DOM text does not
        print(f"   {n} steg")
        for i in range(n - 1):
            more = pg.locator(".wz-more > button")
            if await more.count(): await more.click(); await pg.wait_for_timeout(150)
            opt = pg.locator(".wz-quiz-opts button").first
            if await opt.count(): await opt.click(); await pg.wait_for_timeout(120)
            await pg.locator(".wz-foot button", has_text="Nästa").click(); await pg.wait_for_timeout(260)
            if errs: print(f"  !! steg {i+2}: {errs[-1][:200]}"); errs.clear()
        await pg.keyboard.press("Escape"); await pg.wait_for_timeout(300)
        print("  ", errs[-2:] or "rent"); errs.clear()

        print("== analysen: flikar och kontroller ==")
        await pg.goto(f"{BASE}/jobs/{job}", wait_until="networkidle"); await pg.wait_for_timeout(6000)
        await click_all(pg, ".viewtabs button", "vy-flik")
        await pg.locator(".viewtabs button", has_text="ANALYS").click(); await pg.wait_for_timeout(800)
        await click_all(pg, ".tabs button", "panel-flik")
        await pg.locator(".tabs button", has_text="MÄNGDER").click(); await pg.wait_for_timeout(500)
        await click_all(pg, ".toolbar button", "verktyg")
        await pg.evaluate("document.fullscreenElement && document.exitFullscreen()")
        await pg.wait_for_timeout(600)
        await click_all(pg, "table tbody tr", "mängdrad", limit=6)
        print("  ", errs[-2:] or "rent"); errs.clear()

        print("== rättelser: alla lägen ==")
        await pg.locator(".tabs button", has_text="RÄTTA").click(); await pg.wait_for_timeout(700)
        # four of the modes act on a chosen run, so one is chosen the way the panel asks for it: by clicking a
        # run in the drawing. Without that they stay disabled and the sweep proves nothing about them.
        hit = await pg.evaluate("""() => {
            const svg = document.querySelector('.viewer svg'); if (!svg) return null;
            const p = [...svg.querySelectorAll('polyline[stroke="transparent"]')];
            if (!p.length) return null;
            // the middle of a bent run's bounding box is not on the run: take a point on the line itself
            const el = p[Math.floor(p.length / 2)];
            const pts = (el.getAttribute('points') || '').trim().split(/\s+/).map(q => q.split(',').map(Number));
            if (pts.length < 2) return null;
            const a = pts[0], b = pts[1];
            const m = el.getScreenCTM();
            const q = svg.createSVGPoint(); q.x = (a[0] + b[0]) / 2; q.y = (a[1] + b[1]) / 2;
            const r = q.matrixTransform(m);
            return { x: r.x, y: r.y, n: p.length };
        }""")
        if hit:
            await pg.mouse.click(hit["x"], hit["y"]); await pg.wait_for_timeout(900)
            on = await pg.evaluate("""() => [...document.querySelectorAll('.card button')]
                .filter(b => !b.disabled).map(b => b.textContent.trim()).slice(0, 8)""")
            print(f"  valde ett rör av {hit['n']} · påslagna lägen: {on}")
        box = await pg.locator(".viewer .page").bounding_box()
        for mode in ("Rita nytt rör", "Sudda", "Förläng", "Byt beteckning", "Rätta mängd"):
            # each mode starts from a clean panel: a draft left over from the last one hides the next button
            for label in ("Gör om", "Ångra"):
                b2 = pg.get_by_role("button", name=label, exact=False)
                if await b2.count():
                    try: await b2.first.click(timeout=1200); await pg.wait_for_timeout(250)
                    except Exception: pass
            btn = pg.get_by_role("button", name=mode, exact=False)
            if not await btn.count():
                print(f"  {mode}: KNAPPEN SAKNAS"); continue
            try:
                await btn.first.click(timeout=2500)
            except Exception as e:
                print(f"  {mode}: gick inte att klicka — {str(e)[:90]}"); continue
            await pg.wait_for_timeout(450)
            x, y = box["x"] + 260, box["y"] + 320
            await pg.mouse.move(x, y); await pg.mouse.down(); await pg.mouse.move(x + 90, y + 40, steps=6)
            await pg.mouse.up(); await pg.wait_for_timeout(350)
            await pg.mouse.click(x + 150, y + 20); await pg.wait_for_timeout(350)
            await pg.mouse.dblclick(x + 210, y + 70); await pg.wait_for_timeout(400)
            await pg.keyboard.press("Escape"); await pg.wait_for_timeout(250)
            alive = len((await pg.inner_text("body")).strip()) > 200
            if errs: print(f"  !! {mode}: {errs[-1][:240]}"); errs.clear()
            else: print(f"  {mode}: rent (sidan lever: {alive})")

        print("== en rättelse hela vägen: rita, namnge, spara, ångra ==")
        # zoomstegen ovan har flyttat sidan utanför rutan: passa in hela sidan igen och mät ritytan på nytt,
        # annars landar klicken utanför skärmen och inget utkast blir till
        await pg.locator(".toolbar button", has_text="Sida").click(); await pg.wait_for_timeout(600)
        box = await pg.locator(".viewer canvas").first.bounding_box()
        await pg.get_by_role("button", name="Rita nytt rör", exact=False).click(); await pg.wait_for_timeout(400)
        x, y = box["x"] + 240, box["y"] + 260
        await pg.mouse.click(x, y); await pg.wait_for_timeout(250)
        await pg.mouse.click(x + 130, y); await pg.wait_for_timeout(250)
        await pg.mouse.dblclick(x + 130, y + 90); await pg.wait_for_timeout(600)
        f = pg.locator("input[placeholder^='t.ex.']")
        if await f.count(): await f.first.fill("KV1-X31-16")
        note = pg.locator("input[placeholder^='Valfritt']")
        if await note.count(): await note.first.fill("provrättelse från rökprovet")
        await pg.wait_for_timeout(250)
        save = pg.get_by_role("button", name="Spara rättelse", exact=False)
        await save.first.click(); await pg.wait_for_timeout(2500)
        saved = "provrättelse" in (await pg.inner_text("body"))
        und = pg.get_by_role("button", name="Ångra", exact=False)
        undone = None
        if await und.count():
            await und.first.click(); await pg.wait_for_timeout(2000)
            undone = "provrättelse" not in (await pg.inner_text("body"))
        print(f"  sparad: {saved} · ångrad: {undone} · fel: {errs[-1][:120] if errs else 'inga'}")
        errs.clear()

        body = (await pg.inner_text("body")).strip()
        print("SIDAN LEVER:", len(body) > 200)
        await b.close()
asyncio.run(main())
