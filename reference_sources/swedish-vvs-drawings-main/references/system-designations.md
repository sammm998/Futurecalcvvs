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

| Code | Swedish | English | Lines |
|---|---|---|---|
| V | Vätska i allmänhet | Liquid, general | 1 |
| KV | Tappkallvatten | Domestic cold water | 1 |
| VV | Tappvarmvatten | Domestic hot water | 1 |
| VVC | Varmvattencirkulation i separat ledning | Domestic hot water circulation, in a separate pipe | 1 |
| VVCi | Varmvattencirkulation i infogad ledning | Domestic hot water circulation, in an integrated (inserted) pipe | 1 |
| S | Spillvatten | Wastewater / soil and waste drainage | 1 |
| D | Dagvatten | Stormwater / surface water | 1 |
| DR | Dränvatten | Subsoil drainage water | 1 |
| VP | Primärt vatten i värmeanläggning | Primary water in a heating installation | 2 |
| VS | Sekundärt vatten i värmeanläggning | Secondary water in a heating installation | 2 |
| Å | Ånga | Steam | 1 |
| K | Kondensat | Condensate | 1 |
| G | Gas i allmänhet | Gas, general | 1 |
| L | Luft (tryckluft, vakuum etc.) | Air (compressed air, vacuum, etc.) | 1 |
| O | Olja | Oil | 1 |
| SL | Säkerhetsledning | Safety line | 1 |
| BRL | Ledning för brandsläckningsändamål | Fire-fighting line | 1 |
| KB | Köldbärare | Cold carrier / brine circuit | 2 |
| KM | Kylmedel | Refrigerant / cooling medium | 2 |
| ÅV | Återvinningskrets | Heat recovery circuit | 2 |
| FV | Fjärrvärme | District heating | 2 |
| FK | Fjärrkyla | District cooling | 2 |
| KP | Köldbärare (alternativ beteckning) | Cold carrier / brine circuit (legend variant) | 2 |
| VÅV | Värmeåtervinning | Heat recovery circuit (legend variant) | 2 |
| FJV | Fjärrvärme (alternativ beteckning) | District heating (legend variant) | 2 |
| FJK | Fjärrkyla (alternativ beteckning) | District cooling (legend variant) | 2 |

## Notes carried from the source

- **VVC** — Labelled separately from VV. VV and VVC run together and look like a supply/return pair, but they are two systems with two labels and usually two dimensions.
- **SL** — Code collision: SL also denotes Slutapparat in ventilation equipment (see side_contractor_equipment).
- **KB** — KP and KS are also used for köldbärare. Index commonly refers to the system: KB1 = wet cooling (våt kyla), KB2 = dry cooling (torr kyla). KP is the same circuit under another legend spelling.
- **KP** — Legend spelling of KB. Code collision: KP also denotes kompensator (expansion joint) as a component symbol - position resolves it.
- **VÅV** — Legend spelling of ÅV.
- **FJV** — Legend spelling of FV.
- **FJK** — Legend spelling of FK.

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
