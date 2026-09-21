# Drawing symbols

Symbols per SIS 32260, which deviates somewhat from the European standard. Older
drawings use older symbol variants — those are listed where the source records
them, because a recogniser trained only on current symbols will miss them on any
renovation project working from original drawings.

## Pipe run symbols

| Code | Swedish | English | Symbol on the drawing |
|---|---|---|---|
| — | Flexibel slang | Flexible hose | Wavy line inserted in the pipe run. |
| — | Ledning som ska rivas | Pipe to be demolished / removed | Line with repeated X marks along it. |
| — | Fallriktning för ledning | Fall direction (gradient) of the pipe | Arrow above the line pointing in the direction of fall. |
| — | Strömningsriktning | Flow direction | Arrowhead drawn on the line itself. |
| KP | Kompensator | Expansion compensator | Small rectangle inserted in the pipe run. |
| PR | Proppad ledning | Plugged / capped pipe end | Pipe terminating in a short perpendicular cap. |
| INK | Inkoppling - inskärning i befintlig ledning | Connection made by cutting into an existing pipe | T-junction on an existing line, labelled INK. |
| ANSL | Anslutning till befintlig avstickare | Connection to an existing branch/spur | T-junction on an existing line, labelled ANSL. |

Notes:

- **KP** — Code collision: KP is also used as an alternative designation for köldbärare.

`INK` (cutting into an existing pipe) and `ANSL` (connecting to an existing
branch) both mark the boundary between existing and new installation. Together
with `BEF` they define what is *not* new-build quantity.

A line with repeated X marks is a pipe to be demolished — a demolition quantity,
counted separately from new installation.

## Valves

Flow through a backventil runs from the unmarked field to the marked field. On a
trevägsventil the marked fields show the controllable opening.

| Code | Swedish | English | Ways | Symbol | Older symbol |
|---|---|---|---|---|---|
| AV | Avstängningsventil, tvåvägs | Shut-off valve, two-way | 2 | Two opposed triangles (bowtie) in the pipe run. | Filled dot with a short stem. |
| SV | Styrventil, tvåvägs | Control valve, two-way | 2 | Single triangle on a stem in the pipe run. |  |
| AV | Avstängningsventil, trevägs | Shut-off valve, three-way | 3 | Bowtie with a third branch on a stem. | Filled dot with a stem on a tee. |
| SV | Styrventil, trevägs | Control valve, three-way | 3 | Bowtie with a marked field and a third branch. | Filled triangle with an arrow stem. |
| AV | Avstängningsventil, fyrvägs | Shut-off valve, four-way | 4 | Four-way cross of triangles. |  |
| SV | Styrventil, fyrvägs | Control valve, four-way | 4 | Four-way cross of triangles with marked fields. |  |
| BV | Backventil | Check valve / non-return valve |  | Bowtie with one field filled. Flow runs from the unmarked to the marked field. | Triangle against a bar, filled or open. |
| SÄV | Säkerhetsventil | Safety relief valve |  | Bowtie with a downward arrow on the stem. |  |
| TV | Tappventil | Draw-off / tap valve |  | Short perpendicular stem with a dot at the pipe. |  |
| AL | Luftavledare | Air vent / air release device |  | Inverted hook on a stem rising from the pipe. |  |
| VAV | Vakuumventil | Vacuum breaker valve |  | Comb of short vertical strokes on the pipe. |  |
| BL | Blandare | Mixer / mixing tap |  | Two dots on the pipe joined by a bracket to a single outlet stem. |  |

## Control devices and actuators

On older drawings the ställdon (actuator) was drawn as a square rather than a circle.

| Code | Swedish | English | Symbol on the drawing | Older symbol |
|---|---|---|---|---|
| RC | Reglercentral | Control unit / controller | Small square with dashed lines rising from it. |  |
| ST | Handställdon | Manual actuator | T shape on the valve stem. |  |
| ST | Övriga ställdon, grundsymbol | Other actuators, base symbol | Circle on the valve stem. | Square on the valve stem. |
| SV | Styrventil, manuell | Control valve, manual | Bowtie with a plain stem. |  |
| SV | Styrventil med automatiskt ställdon | Control valve with automatic actuator | Bowtie with a circle (actuator) on the stem. | Bowtie with a square on the stem. |

## Apparatus

General convention: a round symbol is used mostly where rotating parts occur; a
rectangle, upright or lying, shows fixed parts.

| Code | Swedish | English | Symbol on the drawing |
|---|---|---|---|
| — | Allmän symbol | General symbol | Circle or rectangle. The circle is used mostly where rotating parts occur; the rectangle (upright or lying) shows fixed parts. |
| VVX | Värmeväxlare | Heat exchanger | Rectangle in the pipe run with an internal chevron/arrow. |
| P | Pump | Pump | Circle with an internal triangle pointing in the flow direction. |
| SIL | Sil, filter | Strainer, filter | Rectangle with hatching. |
| — | Radiator, värmare | Radiator, heater | Long narrow rectangle. |
| EXP | Expansionskärl | Expansion vessel | Rectangle with EXP written inside the symbol. |
| — | Dusch | Shower | Small triangle on a vertical stem. |
| SG | Shuntgrupp | Shunt group / mixing group |  |
| VXV | Växelventil | Changeover / diverting valve |  |
| STPR | Stuprör | Rainwater downpipe |  |

## Sanitary fixtures

These have no dedicated symbol — they are drawn in a simplified way (förenklat
ritsätt) and identified by code plus an index that distinguishes appliance and
mixer types, e.g. `TS1`, `VK2`.

| Code | Swedish | English |
|---|---|---|
| DB | Diskbänk | Kitchen sink unit / worktop with sink |
| UB | Utslagsback | Slop sink / cleaner's sink |
| TS | Tvättställ, tvättho | Washbasin, wash trough |
| BK | Badkar | Bathtub |
| DK | Duschkar | Shower tray |
| VK | Klosett | WC / toilet |
| U | Urinalskål, urinränna | Urinal bowl, urinal trough |
| DF | Dricksvattenfontän | Drinking fountain |
| DM | Diskmaskin | Dishwasher |
| TM | Tvättmaskin | Washing machine |
| SLH | Slanghylla | Hose shelf / hose reel rack |
| VVB | Tappvattenvärmare (förr varmvattenberedare) | Domestic water heater (formerly called varmvattenberedare) |

Notes:

- **DB** — Code collision: DB also denotes Dagvattenbrunn (see drainage_wells).

## Wells, gullies and separators

The general well symbol is a circle or a rectangle.

| Code | Swedish | English | Symbol on the drawing |
|---|---|---|---|
| B | Brunn i allmänhet | Well / gully, general | Circle or rectangle. |
| DB | Dagvattenbrunn | Stormwater gully |  |
| NB | Nedstigningsbrunn | Manhole (man-entry chamber) |  |
| SB | Spolbrunn | Rodding / flushing chamber |  |
| TB | Tillsynsbrunn | Inspection chamber |  |
| DRB | Dräneringsbrunn | Drainage chamber |  |
| — | Avskiljare | Separator (e.g. oil or grease separator) | Rectangle with a vertical divider in the pipe run. |
| RA | Rensanordning | Rodding eye / cleaning device |  |

Notes:

- **DB** — Code collision: DB also denotes Diskbänk among sanitary fixtures.
- **TB** — Code collision: TB also denotes Kylbaffel med tilluft.

## Sensors and instruments

`G` prefix = givare (sensor), `M` prefix = mätinstrument (measuring instrument).
The second letter is the measured quantity.

| Sensor | Instrument | Swedish | English |
|---|---|---|---|
| GF | MF | Flöde | Flow |
| GL | ML | Läge, nivå, vinkel, längd | Position, level, angle, length |
| GM | MM | Fuktighet | Humidity |
| GP | MP | Tryck | Pressure |
| GS | MS | Hastighet, varvtal | Speed, rotational speed |
| GT | MT | Temperatur | Temperature |
| GX | MX | Övrigt | Other |

Drawn as small symbols on a stem from the pipe: a cone for a givare, a circle
with a pointer for a visande instrument, a circle with an S for a skrivande
(recording) instrument, a slash for a rörtermometer, and a bowtie with a circle
for a styrventil med motor.

## Side contractor equipment

Mostly ventilation equipment installed under another contract — relevant to a
pipe takeoff mainly as scope boundary.

| Code | Swedish | English |
|---|---|---|
| LV | Luftvärmare (i ventilationsutrustning) | Air heater (in ventilation equipment) |
| LK | Luftkylare (i ventilationsutrustning) | Air cooler (in ventilation equipment) |
| SL | Slutapparat (i ventilationsutrustning) | Terminal unit (in ventilation equipment) |
| EB | Kylbaffel (utan tilluft) | Chilled beam (without supply air) |
| TB | Kylbaffel (med tilluft) | Chilled beam (with supply air) |
| LVE | Lufteftervärmare (i ventilationsutrustning) | Air reheater (in ventilation equipment) |
| IL | Inspektionslucka | Inspection hatch / access panel |

Notes:

- **SL** — Code collision: SL also denotes Säkerhetsledning as a system designation.
- **TB** — Code collision: TB also denotes Tillsynsbrunn among wells.
