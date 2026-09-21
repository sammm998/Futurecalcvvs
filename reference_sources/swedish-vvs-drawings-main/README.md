# swedish-vvs-drawings

A Claude Code skill: domain reference for reading Swedish VVS (Värme, Ventilation, Sanitet — heating, ventilation, plumbing) construction drawings. Built for writing and debugging software that turns pipes, labels and dimensions on a *ritning* into structured data (mängdavtagning / takeoff).

Covers systembeteckningar, pipe label grammars (`KV-22`, `VS1-S13-12/W`, `S1-110`), line types, vertical stroke notation, valve and apparatus symbols, ritningsnummer, and contractor and discipline codes — from SIS 32260, Bygghandlingar 90 and AMA, plus a survey of real sheets from nine design offices (2018–2026).

## Install

Clone into the Claude Code skills directory:

```bash
git clone git@github.com:michalnikolajuk/swedish-vvs-drawings.git ~/.claude/skills/swedish-vvs-drawings
```

## Layout

| Path | What it is |
| --- | --- |
| `SKILL.md` | The skill itself — frontmatter trigger plus the prose Claude reads |
| `data/*.json` | Machine-readable source of truth: 24 code tables with `notes` flagging collisions |
| `references/*.md` | Generated prose: why a rule exists and how it fails |
| `scripts/*.py` | Runnable helpers (stdlib only, Python 3.11+) |

## Scripts

```bash
python scripts/parse_pipe_label.py VS1-S13-12/W VS111-55-16 KV11-25
python scripts/lookup_code.py DB TB SL
python scripts/assign_label.py --demo
```

- `parse_pipe_label.py` — tokenizes a label into system, number, unresolved material fields and dimension.
- `lookup_code.py` — resolves a code across every category, returning *all* meanings (`DB` is both a kitchen sink and a stormwater gully).
- `assign_label.py` — decides which of two candidate segments a label at a junction describes.
- `vvs_kb.py` — shared JSON loader.

## Editing

`references/*.md` is generated. Edit the JSON, then regenerate:

```bash
python scripts/build_references.py
```

## The rule that matters

Swedish drawing practice is conventional, not guaranteed. Where a sheet carries a legend (FÖRKLARINGAR / RITNINGSBETECKNINGAR), the legend wins over these tables. Treat a table miss as *unknown*, not *invalid*, and surface it for human review — a pipeline that silently drops what it cannot parse produces a confident, wrong quantity.
