#!/usr/bin/env python3
"""Regenerate references/*.md from data/*.json.

The prose intros live in this script; the tables come from the JSON. Editing a
table by hand would drift from the source of truth, so edit the JSON and re-run:

    python scripts/build_references.py
"""

from __future__ import annotations

from pathlib import Path

from vvs_kb import load_all

ROOT = Path(__file__).resolve().parent.parent
REFS = ROOT / "references"

KB = load_all()


def esc(text) -> str:
    return str(text or "").replace("|", r"\|").replace("\n", " ")


def table(category: str, columns: list[tuple[str, str]]) -> str:
    """Markdown table for a category. columns = [(header, json_field), ...]"""
    doc = KB[category]
    head = "| " + " | ".join(h for h, _ in columns) + " |"
    rule = "|" + "|".join("---" for _ in columns) + "|"
    rows = []
    for entry in doc.get("entries", []):
        cells = []
        for _, field in columns:
            value = entry.get(field)
            if field == "code" and not value:
                value = "—"
            cells.append(esc(value))
        rows.append("| " + " | ".join(cells) + " |")
    return "\n".join([head, rule, *rows])


def note_lines(category: str) -> str:
    """Collision and free-text notes for a category, as a bullet list."""
    out = []
    for entry in KB[category].get("entries", []):
        if entry.get("notes"):
            code = entry.get("code") or entry.get("term_sv")
            out.append(f"- **{code}** — {esc(entry['notes'])}")
    return "\n".join(out)


CODE_SV_EN = [("Code", "code"), ("Swedish", "term_sv"), ("English", "term_en")]
SYMBOL_COLS = CODE_SV_EN + [("Symbol on the drawing", "symbol_description")]


def write(name: str, body: str) -> None:
    (REFS / name).write_text(body.strip() + "\n", encoding="utf-8")
    print(f"wrote references/{name}")


# --------------------------------------------------------------------------
write("system-designations.md", f"""
# Systembeteckningar

The system part of a pipe label. Written on the drawing immediately before the
dimension: `KV-22`, `VS2-40`, `S1-160`.

`Lines` is the number of physical pipes the label belongs to. For circulating
circuits — heat carrier, cold carrier, recovery, district heating and cooling —
framledning and returrör always travel as a pair, so a labelled run of one of
these systems has a partner somewhere. How the sheet draws that pair decides what
to do with it: two parallel lines with the label on only one of them means copy
the label to the unlabelled twin and measure both, while a single line standing
for the pair means double the measured length. Doing both, or neither, is the
field most likely to be lost when someone retypes this table into code, and it
halves or doubles the pipe length for every affected system.

Systems with `Lines` 1 — tappvatten (KV, VV, VVC), spillvatten (S), dagvatten (D)
and the rest — label every drawn pipe individually. VV and VVC in particular look
like a supply/return pair and are not one: two systems, two labels, usually two
dimensions.

{table("system_designation", CODE_SV_EN + [("Lines", "line_count")])}

## Notes carried from the source

{note_lines("system_designation")}

## Index semantics

An index digit may follow the system code (`KV1-35`, `VS2-40`, `KB2-50`). No
standard defines it — the drawing or the beskrivning does. The usual readings:

- **KV, VV, VVC, S, D** — index identifies the pipe material (rörmaterial)
- **VS, KB, G** — index identifies the system group: `VS1` radiators, `VS2`
  ventilation; `KB1` wet cooling (våt kyla), `KB2` dry cooling (torr kyla)

Carry the index through your model unresolved and resolve it per project. Where
a designation system also encodes insulation or other properties, the drawing
carries its own legend and that legend is authoritative.

## What is not in the label

Rörmaterial, fogmetod and isolering come from the VVS-beskrivning, never from
the label. A takeoff from drawings alone is length per system and dimension —
not yet priceable.
""")

# --------------------------------------------------------------------------
write("symbols.md", f"""
# Drawing symbols

Symbols per SIS 32260, which deviates somewhat from the European standard. Older
drawings use older symbol variants — those are listed where the source records
them, because a recogniser trained only on current symbols will miss them on any
renovation project working from original drawings.

## Pipe run symbols

{table("pipe_symbol", SYMBOL_COLS)}

Notes:

{note_lines("pipe_symbol")}

`INK` (cutting into an existing pipe) and `ANSL` (connecting to an existing
branch) both mark the boundary between existing and new installation. Together
with `BEF` they define what is *not* new-build quantity.

A line with repeated X marks is a pipe to be demolished — a demolition quantity,
counted separately from new installation.

## Valves

Flow through a backventil runs from the unmarked field to the marked field. On a
trevägsventil the marked fields show the controllable opening.

{table("valve", CODE_SV_EN + [("Ways", "ways"), ("Symbol", "symbol_description"), ("Older symbol", "older_symbol")])}

## Control devices and actuators

On older drawings the ställdon (actuator) was drawn as a square rather than a circle.

{table("control_device", SYMBOL_COLS + [("Older symbol", "older_symbol")])}

## Apparatus

General convention: a round symbol is used mostly where rotating parts occur; a
rectangle, upright or lying, shows fixed parts.

{table("apparatus", SYMBOL_COLS)}

## Sanitary fixtures

These have no dedicated symbol — they are drawn in a simplified way (förenklat
ritsätt) and identified by code plus an index that distinguishes appliance and
mixer types, e.g. `TS1`, `VK2`.

{table("sanitary_fixture", CODE_SV_EN)}

Notes:

{note_lines("sanitary_fixture")}

## Wells, gullies and separators

The general well symbol is a circle or a rectangle.

{table("drainage_well", SYMBOL_COLS)}

Notes:

{note_lines("drainage_well")}

## Sensors and instruments

`G` prefix = givare (sensor), `M` prefix = mätinstrument (measuring instrument).
The second letter is the measured quantity.

{table("sensor_instrument", [("Sensor", "sensor_code"), ("Instrument", "instrument_code"), ("Swedish", "quantity_sv"), ("English", "quantity_en")])}

Drawn as small symbols on a stem from the pipe: a cone for a givare, a circle
with a pointer for a visande instrument, a circle with an S for a skrivande
(recording) instrument, a slash for a rörtermometer, and a bowtie with a circle
for a styrventil med motor.

## Side contractor equipment

Mostly ventilation equipment installed under another contract — relevant to a
pipe takeoff mainly as scope boundary.

{table("side_contractor_equipment", CODE_SV_EN)}

Notes:

{note_lines("side_contractor_equipment")}
""")

# --------------------------------------------------------------------------
numbering = KB["drawing_numbering"]
parts = "\n".join(
    f"| {esc(p['part'])} | {esc(p['part_en'])} | `{esc(p['example'])}` | {esc(p['note'])} |"
    for p in numbering["structure"]["parts"]
)
num_rules = "\n".join(f"- {esc(r['rule_en'])}" for r in numbering["rules"])
title_fields = "\n".join(f"- {esc(f)}" for f in numbering["example_title_block_fields"])
change = KB["document_change_handling"]
drawing_places = "\n".join(
    f"- {esc(p['en'])} ({esc(p['sv'])})" for p in change["drawing_change_markers"]["places"]
)

write("drawing-metadata.md", f"""
# Drawing identity, classification and revisions

Everything that identifies *which* drawing you are looking at and *what state*
it is in. For an extraction pipeline this is the indexing layer: it decides
which floor, which discipline and which revision a set of quantities belongs to.

## Ritningsnummer

Three parts separated by hyphens; the classification part may be omitted, so
both `{numbering["structure"]["full_example"]}` and
`{numbering["structure"]["short_example"]}` are valid drawing numbers.

| Part | English | Example | Note |
|---|---|---|---|
{parts}

{num_rules}

## Responsible party (first field)

{table("discipline_code", CODE_SV_EN)}

Single letters here collide with system designations — `V`, `G`, `K`, `L` are
both. Position resolves it: a discipline code opens a drawing number in the
title block; a system designation sits on a pipe followed by `-<dimension>`.

## Drawing content (two digits)

{table("drawing_content_classification", CODE_SV_EN)}

For VVS drawings the content code is most often **50** or **57**. Code 50 is
used when several kinds of installation share one drawing, which makes it the
usual code for a rörentreprenad.

## Drawing category (one digit, SS 32266)

{table("drawing_category", CODE_SV_EN)}

## Document status

Written in the title block (namnruta). Status decides whether quantities are
indicative or contractual.

{table("document_status", CODE_SV_EN)}

## Revisions

A change is marked in several places at once:

{drawing_places}

Tender documents are changed by a **KFU** (kompletterande förfrågningsunderlag);
construction documents by an **Ändrings-PM**. Both are numbered in one sequence.

{esc(change["takeoff_implication"])}

## Title block fields

{title_fields}

## Level and reference abbreviations

{table("level_reference", CODE_SV_EN)}
""")

# --------------------------------------------------------------------------
rules = KB["document_rule"]
rule_text = []
for entry in rules["entries"]:
    rule_text.append(f"### {esc(entry.get('title_en'))}\n")
    if entry.get("text_en"):
        rule_text.append(esc(entry["text_en"]) + "\n")
    if entry.get("items_en"):
        rule_text.extend(f"- {esc(i)}" for i in entry["items_en"])
        rule_text.append("")
    if entry.get("takeoff_implication"):
        rule_text.append(f"*Implication:* {esc(entry['takeoff_implication'])}\n")

as_built = KB["as_built_requirements"]
ab_reqs = "\n".join(f"- {esc(r['en'])}" for r in as_built["requirements"])
ab_extra = "\n".join(f"- {esc(r['en'])}" for r in as_built.get("additional_rules", []))

write("document-context.md", f"""
# Document context: precedence, as-builts and DoU

Why this matters to an extractor: a drawing is one document in a set, and it is
not the authoritative one. Knowing the hierarchy tells you when a
drawing-derived number should lose to something else.

{chr(10).join(rule_text)}

## Standards referenced

{chr(10).join(f"- **{esc(s['id'])}** — {esc(s['scope'])}" + (f" {esc(s.get('note'))}" if s.get("note") else "") for s in KB["meta"]["standards_referenced"]) if "meta" in KB else ""}

## As-built documents (relationshandlingar)

Source: {esc(as_built.get("source"))}

{ab_reqs}

{ab_extra}

{esc(as_built["coordinated_as_builts"]["text_en"])}

## Operation and maintenance (DoU)

{esc(KB["dou_instructions"]["legal_basis_en"])}

The industry standard is *{esc(KB["dou_instructions"]["standard"]["title_sv"])}*
({esc(KB["dou_instructions"]["standard"]["publisher"])},
{KB["dou_instructions"]["standard"]["year"]}).
""")
