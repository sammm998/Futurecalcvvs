"""Mängdningens eget arbetsbord: välj blad, kalibrera, mät, räkna, se summorna.

Kör mot serve_seeded.py på 127.0.0.1:8077. Provet klickar som en människa och läser av vad sidan svarar; det
som mäts räknas på servern, så siffran i listan är serverns och inte webbläsarens.
"""
import asyncio
import os
import re
import sys

from playwright.async_api import async_playwright

SP = os.environ.get("SP", os.path.dirname(os.path.abspath(__file__)))
job, tok = open(f"{SP}/ui/job.txt").read().split()
BASE = "http://127.0.0.1:8077"
errs: list[str] = []
found: list[str] = []


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

        print("== mängda: fliken i sidomenyn ==")
        await pg.goto(f"{BASE}/projekt", wait_until="networkidle"); await pg.wait_for_timeout(600)
        link = pg.locator(".side nav a", has_text="Mängda")
        print(f"  fliken finns: {await link.count() > 0}")
        if not await link.count():
            found.append("ingen Mängda-flik i sidomenyn")
        else:
            await link.first.click(); await pg.wait_for_timeout(900)
        note("mängda-fliken")

        print("== mängda: välj ett blad ==")
        first = pg.locator(".list .item .ttl").first
        if not await first.count():
            found.append("inga blad att mängda")
        else:
            await first.click(); await pg.wait_for_timeout(2500)
        note("valde blad")
        on = "/mangda/" in pg.url and await pg.locator(".tk-grid").count() > 0
        print(f"  arbetsbordet öppnat: {on}")
        if not on:
            found.append("mängdningsbordet öppnades inte")

        canvas = pg.locator(".tk-sheet canvas").first
        for _ in range(40):
            await pg.wait_for_timeout(400)
            if await canvas.count() and (await canvas.bounding_box()):
                break
        # passa in hela sidan innan något ritas: annars ligger den där provet klickar utanför rutan
        fit = pg.locator(".tk-sheet .toolbar button", has_text="Sida")
        if await fit.count():
            await fit.first.click(); await pg.wait_for_timeout(800)
        box = await canvas.bounding_box()
        print(f"  bladet ritat: {bool(box)}")
        if not box:
            found.append("bladet ritades aldrig")
            print(f"SIDAN LEVER: {len((await pg.inner_text('body')).strip()) > 200}")
            print(f"FYND: {len(found)}")
            for f in found:
                print("  -", f)
            await b.close()
            return

        print("== kalibrera skalan ==")
        await pg.get_by_role("button", name=re.compile("Kalibrera skala")).click(); await pg.wait_for_timeout(400)
        x, y = box["x"] + box["width"] * 0.25, box["y"] + box["height"] * 0.30
        step = max(80.0, box["width"] * 0.18)
        await pg.mouse.click(x, y); await pg.wait_for_timeout(200)
        await pg.mouse.dblclick(x + step, y); await pg.wait_for_timeout(500)
        await pg.locator(".tk-side input").first.fill("10")
        await pg.get_by_role("button", name="Spara skalan").click(); await pg.wait_for_timeout(1500)
        note("kalibrering")
        body = (await pg.inner_text("body")).lower()
        print(f"  skalan uppmätt: {'uppmätt' in body}")
        if "uppmätt" not in body:
            found.append("kalibreringen slog inte igenom")

        print("== mät en längd och räkna två saker ==")
        await pg.locator(".tk-tools button", has_text="Längd").click(); await pg.wait_for_timeout(300)
        await pg.mouse.click(x, y + step * 0.5); await pg.wait_for_timeout(200)
        await pg.mouse.dblclick(x + step * 1.2, y + step * 0.5); await pg.wait_for_timeout(500)
        await pg.get_by_role("button", name="Spara markering").click(); await pg.wait_for_timeout(1500)
        note("sparade längd")
        await pg.locator(".tk-tools button", has_text="Antal").click(); await pg.wait_for_timeout(300)
        for k in range(2):
            await pg.mouse.click(x + 30 + k * 30, y + step); await pg.wait_for_timeout(200)
        await pg.mouse.dblclick(x + 30 + 2 * 30, y + step); await pg.wait_for_timeout(400)
        await pg.get_by_role("button", name="Spara markering").click(); await pg.wait_for_timeout(1500)
        note("sparade antal")

        rows = await pg.locator(".tk-side table.qty tbody tr").count()
        stats = await pg.locator(".tk-side .adm-stat .v").all_inner_texts()
        print(f"  rader i listan: {rows} · summor: {stats}")
        if rows < 2:
            found.append("markeringarna hamnade inte i listan")
        metres = stats[0] if stats else "–"
        if metres in ("–", "0,00"):
            found.append(f"längden summerades inte ({metres})")
        print(f"  längden summerad: {metres}")

        body = (await pg.inner_text("body")).strip()
        print("SIDAN LEVER:", len(body) > 200)
        print(f"FYND: {len(found)}")
        for f in found:
            print("  -", f)
        await b.close()

asyncio.run(main())
