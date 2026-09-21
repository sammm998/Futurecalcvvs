"""CAD-rummet: rita en fråga på bladet, arbeta listan, stäng frågan.

Kör mot serve_seeded.py på 127.0.0.1:8077. Provet klickar som en människa och läser av vad sidan svarar; det
som mäts och sparas räknas på servern, så det listan visar är serverns svar och inte webbläsarens.
"""
import asyncio
import os
import time

from playwright.async_api import async_playwright

SP = os.environ.get("SP", os.path.dirname(os.path.abspath(__file__)))
job, tok = open(f"{SP}/ui/job.txt").read().split()
BASE = "http://127.0.0.1:8077"
errs: list[str] = []
found: list[str] = []
# Provet får köras om mot samma seedade tjänst: frågan får ett eget märke så att sökningen hittar just den här
# körningens rad och inte gårdagens.
STAMP = str(int(time.time()) % 100000)
SUBJECT = f"Saknad avstängning {STAMP}"


def note(label):
    if errs:
        found.append(f"{label}: {errs[-1][:200]}")
        print(f"  !! {label}: {errs[-1][:200]}")
        errs.clear()


async def main():
    async with async_playwright() as p:
        exe = os.environ.get("CHROME") or "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
        b = await p.chromium.launch(executable_path=exe if os.path.exists(exe) else None)
        ctx = await b.new_context(viewport={"width": 1500, "height": 940})
        pg = await ctx.new_page()
        pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
        pg.on("pageerror", lambda e: errs.append(str(e)))
        await pg.goto(f"{BASE}/login", wait_until="networkidle")
        await pg.evaluate(f"localStorage.setItem('vvs_token', '{tok}')")

        print("== cad: fliken i sidomenyn ==")
        await pg.goto(f"{BASE}/projekt", wait_until="networkidle"); await pg.wait_for_timeout(600)
        link = pg.locator(".side nav a", has_text="CAD")
        print(f"  fliken finns: {await link.count() > 0}")
        if not await link.count():
            found.append("ingen CAD-flik i sidomenyn")
        else:
            await link.first.click(); await pg.wait_for_timeout(2500)
        note("cad-fliken")

        print("== välj en handling ==")
        first = pg.locator(".list .item .ttl").first
        if not await first.count():
            found.append("ingen handling att granska")
        else:
            await first.click(); await pg.wait_for_timeout(2500)
        on = "/cad/" in pg.url and await pg.locator(".rv-grid").count() > 0
        print(f"  cad-rummet öppnat: {on}")
        if not on:
            found.append("cad-rummet öppnades inte")
        note("öppnade rummet")

        canvas = pg.locator(".rv-sheet canvas").first
        for _ in range(40):
            await pg.wait_for_timeout(400)
            if await canvas.count() and (await canvas.bounding_box()):
                break
        fit = pg.locator(".rv-sheet .toolbar button", has_text="Sida")
        if await fit.count():
            await fit.first.click(); await pg.wait_for_timeout(800)
        box = await canvas.bounding_box() if await canvas.count() else None
        print(f"  bladet ritat: {bool(box)}")
        if not box:
            found.append("bladet ritades aldrig")
            print(f"FYND: {len(found)}")
            for f in found:
                print("  -", f)
            await b.close()
            return

        print("== rita en fråga ==")
        await pg.locator(".rv-side .tk-tools button", has_text="Moln").click(); await pg.wait_for_timeout(300)
        x, y = box["x"] + box["width"] * 0.3, box["y"] + box["height"] * 0.3
        step = max(70.0, box["width"] * 0.12)
        await pg.mouse.click(x, y); await pg.wait_for_timeout(150)
        await pg.mouse.click(x + step, y); await pg.wait_for_timeout(150)
        await pg.mouse.dblclick(x + step, y + step); await pg.wait_for_timeout(400)
        await pg.locator(".rv-side input").first.fill(SUBJECT)
        await pg.locator(".rv-side textarea").first.fill("Var stängs stammen av?")
        await pg.get_by_role("button", name="Spara markering").click(); await pg.wait_for_timeout(1800)
        note("sparade fråga")

        rows = await pg.locator(".mk-table tbody tr").count()
        print(f"  rader i markeringslistan: {rows}")
        if rows < 1:
            found.append("frågan hamnade inte i markeringslistan")

        body = (await pg.inner_text("body"))
        print(f"  ämnet står i listan: {SUBJECT in body}")
        if SUBJECT not in body:
            found.append("ämnet syns inte i listan")

        print("== sök, sortera och stäng frågan ==")
        await pg.locator(".mk-filters input").first.fill(STAMP); await pg.wait_for_timeout(500)
        kvar = await pg.locator(".mk-table tbody tr").count()
        print(f"  kvar efter sökning: {kvar}")
        if kvar != 1:
            found.append(f"sökningen gav {kvar} rader, väntade en")
        await pg.locator(".mk-filters input").first.fill(""); await pg.wait_for_timeout(400)

        await pg.locator(".mk-table th.sortable", has_text="Ämne").click(); await pg.wait_for_timeout(300)
        note("sortering")


        # stäng den här körningens fråga från dess egen rad, och se att sammanställningen räknar en till godkänd
        fore = await pg.locator(".rv-stats .adm-stat .v").all_inner_texts()
        await pg.locator(".mk-filters input").first.fill(STAMP); await pg.wait_for_timeout(500)
        sel = pg.locator(".mk-table tbody tr select").first
        await sel.select_option("godkand"); await pg.wait_for_timeout(1500)
        note("satte status")
        efter = await pg.locator(".rv-stats .adm-stat .v").all_inner_texts()
        okej = len(efter) > 2 and int(efter[2]) == int(fore[2] or 0) + 1
        print(f"  godkända: {fore[2] if len(fore) > 2 else '?'} -> {efter[2] if len(efter) > 2 else '?'}")
        if not okej:
            found.append(f"godkända räknades inte ({fore} -> {efter})")
        await pg.locator(".mk-filters input").first.fill(""); await pg.wait_for_timeout(400)

        print("== urvalet följer mellan lista och blad ==")
        # den sparade frågan är redan vald; ett klick på samma rad släpper den, så den släpps först och tas sedan
        if await pg.locator(".mk-table tbody tr.selected").count():
            await pg.locator(".mk-table tbody tr.selected").first.click(); await pg.wait_for_timeout(500)
        await pg.locator(".mk-table tbody tr").first.click(); await pg.wait_for_timeout(900)
        chosen = await pg.locator(".mk-table tbody tr.selected").count()
        panel = await pg.locator(".rv-side .card").count()
        print(f"  vald rad: {chosen} · paneler i sidan: {panel}")
        if chosen != 1:
            found.append("raden markerades inte när den valdes")
        if panel < 2:
            found.append("detaljpanelen för den valda markeringen visades inte")
        note("urval")

        body = (await pg.inner_text("body")).strip()
        print("SIDAN LEVER:", len(body) > 200)
        print(f"FYND: {len(found)}")
        for f in found:
            print("  -", f)
        await b.close()

asyncio.run(main())
