"""ABT 06 - totalentreprenad: det som räknas på A-planerna i stället för att mätas på installationsritningarna.

I en totalentreprenad projekterar entreprenören själv. Det som finns att räkna på är arkitektens planer: rummen,
deras ytor, koderna vid inredningen och symbolerna som upprepas. Det här paketet läser det ur ritningarnas egen
text och geometri. Inget här rör VVS-läsningen.
"""


READER = 3      # the version of what read_document returns; a reading kept from an older version is read again


def read_document(path: str, pages: list[int] | None = None) -> dict:
    """Rooms, units and symbols of a PDF in one pass over its pages: the text of a page is read once and serves
    all three."""
    import statistics

    import pymupdf
    from .rooms import read_rooms, register, signature, text_lines
    from .symbols import MIN_REPEAT, read_symbols
    from .units import name_of, read_units
    by_page: dict[int, list[dict]] = {}
    units: list[dict] = []
    legends: dict[str, dict] = {}
    with pymupdf.open(path) as doc:
        read: list[tuple] = []
        heights: dict[int, float] = {}
        for pno, page in enumerate(doc):
            if pages is not None and pno not in pages:
                continue
            lines = text_lines(page)
            read.append((pno, page, lines))
            if lines:
                heights[pno] = statistics.median(ln.size for ln in lines)
            rooms = read_rooms(page, pno, lines)
            if rooms:
                by_page[pno] = [r.as_dict() for r in rooms]
            got, own = read_units(page, pno, lines, rooms)
            units.extend(u.as_dict() for u in got)
            for code, term in own.items():
                legends.setdefault(code, {"term": term, "page": pno})
        symbols = read_symbols(read, heights)
    seen: dict[str, int] = {}
    summary = []
    for pno, rs in sorted(by_page.items()):
        sig = signature(rs)
        same = seen.get(sig)
        seen.setdefault(sig, pno)
        summary.append({"page": pno, "signature": sig, "same_as": same, "counted": same is None,
                        "rooms": sum(1 for r in rs if r["kind"] == "rum"),
                        "apartments": sum(1 for r in rs if r["kind"] == "lagenhet"),
                        "area_m2": round(sum(r["area_m2"] for r in rs if r["kind"] != "summa"), 2)})
    counted = {p["page"] for p in summary if p["counted"]}
    reg = register([r for pno in sorted(by_page) if pno in counted for r in by_page[pno]])
    for u in units:
        u["name"], u["name_source"] = name_of(u["code"], {k: v["term"] for k, v in legends.items()})
    # a page is read for what it gives: its rooms, its units, or enough copies of repeated symbols to be a plan
    on_page: dict[int, int] = {}
    for g in symbols:
        if g["count"] < MIN_REPEAT and not g["legend"]:
            continue
        for s in g["instances"]:
            on_page[s["page"]] = on_page.get(s["page"], 0) + 1
    priced = sorted(set(by_page) | {u["page"] for u in units} | {p for p, n in on_page.items() if n >= MIN_REPEAT})
    reg.update({"pages": summary, "labels": sum(len(v) for v in by_page.values()), "by_page": by_page,
                "units": units, "legend": legends, "symbols": symbols, "priced_pages": priced, "reader": READER})
    return reg
