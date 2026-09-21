# Drawing identity, classification and revisions

Everything that identifies *which* drawing you are looking at and *what state*
it is in. For an extraction pipeline this is the indexing layer: it decides
which floor, which discipline and which revision a set of quantities belongs to.

## Ritningsnummer

Three parts separated by hyphens; the classification part may be omitted, so
both `V-56-1-124` and
`V-124` are valid drawing numbers.

| Part | English | Example | Note |
|---|---|---|---|
| Ansvarig part | Responsible party / discipline | `V` | One letter (or two, e.g. SK). |
| Klassifikation - ritningens innehåll | Classification - drawing content | `56` | Two digits, huvudgrupp + delgrupp. |
| Klassifikation - redovisningssätt | Classification - drawing category / presentation type | `1` | One digit. |
| Numrering | Number | `124` | Location-coded or sequential. |

- For VVS-ritningar the content code is most often 50 or 57. Code 50 is used when several kinds of installation (e.g. heating, tappvatten and drainage) are shown on the same ritning, which makes it suitable for pipework installations (rörentreprenad).
- Drawing numbering is generally coordinated between disciplines (A, E, V, etc.). In large projects numbers are built on a 'lägeskod' (location code) - e.g. the number 124 can mean building 1, building part 2, storey 4.
- Drawings can also be numbered sequentially. All such numbers must contain the same number of digits and can be divided into number series, e.g. 101-199 or 201-299 for different groups of drawings.

## Responsible party (first field)

| Code | Swedish | English |
|---|---|---|
| A | Arkitekt | Architect |
| I | Inredningsarkitekt | Interior architect |
| E | Elprojektör | Electrical designer |
| H | Hissprojektör | Lift designer |
| SK | Storköksprojektör | Commercial kitchen designer |
| G | Geotekniker | Geotechnical engineer |
| K | Byggnadskonstruktör | Structural engineer |
| L | Landskapsarkitekt | Landscape architect |
| M | Markprojektör | Site/ground designer |
| R | VA-projektör | Water and sewage (VA) designer |
| V | VVS-projektör | VVS designer |

Single letters here collide with system designations — `V`, `G`, `K`, `L` are
both. Position resolves it: a discipline code opens a drawing number in the
title block; a system designation sits on a pipe followed by `-<dimension>`.

## Drawing content (two digits)

| Code | Swedish | English |
|---|---|---|
| 50 | Sammansatt redovisning | Combined presentation |
| 51 | VA m.m. i mark (utanför hus) | Water and sewage etc. in the ground (outside the building) |
| 52 | Försörjningssystem | Supply systems |
| 53 | Avloppsvattensystem m.m. | Wastewater systems etc. |
| 54 | Brandsläckningssystem | Fire-fighting systems |
| 55 | Kylsystem | Cooling systems |
| 56 | Värmesystem | Heating systems |
| 57 | Luftbehandlingssystem | Air handling systems |
| 81 | Styr- och övervakning | Control and monitoring |
| 82 | Styr- och övervakning | Control and monitoring |

For VVS drawings the content code is most often **50** or **57**. Code 50 is
used when several kinds of installation share one drawing, which makes it the
usual code for a rörentreprenad.

## Drawing category (one digit, SS 32266)

| Code | Swedish | English |
|---|---|---|
| -0 | Sammansatta ritningar | Composite drawings |
| -1 | Planritningar | Plan drawings |
| -2 | Sektioner | Sections |
| -3 | Fasadritningar | Elevation drawings |
| -4 | Uppställningsritningar | Arrangement / installation layout drawings |
| -5 | Förteckningsritningar | Schedule drawings |
| -6 | Detaljritningar | Detail drawings |
| -7 | Samordningsritningar | Coordination drawings |
| -8 | Scheman | Schematics / diagrams |

## Document status

Written in the title block (namnruta). Status decides whether quantities are
indicative or contractual.

| Code | Swedish | English |
|---|---|---|
| PH | Programhandling | Programme document |
| SH | Systemhandling | System document |
| — | Preliminär handling | Preliminary document |
| FU | Förfrågningsunderlag | Tender documents |
| — | Bygghandling | Construction document |
| — | Relationshandling | As-built document |

## Revisions

A change is marked in several places at once:

- on the drawing at the point of change (in a revision 'cloud') (på ritningen vid ändringsställe (i "moln"))
- in the revision table of the drawing's title block (på ritningens namnruta i ändringstabell)
- in the title block, in the space for the revision designation (på ritningens namnruta i plats för ändringsbeteckning)
- in the document list / drawing list (i handlingsförteckning/ritningsförteckning)
- in the KFU or the PM (i KFU/PM)

Tender documents are changed by a **KFU** (kompletterande förfrågningsunderlag);
construction documents by an **Ändrings-PM**. Both are numbered in one sequence.

A takeoff pipeline must version drawings by ändringsbeteckning (A, B, C, D ...) and re-run affected quantities when a KFU or Ändrings-PM is issued. Revision clouds mark the regions to re-measure.

## Title block fields

- Ändringstabell: BET / ANT / ÄNDRINGEN AVSER / DATUM / SIGN
- Handlingsstatus (e.g. PRELIMINÄR HANDLING, FÖRFRÅGNINGSUNDERLAG, BYGGHANDLING, RELATIONSHANDLING)
- Projekt / fastighet
- Discipline contact rows: A Arkitekt, K Konstruktör, V VVS-konsult, E El-konsult, L Landskap, Konsult (the responsible discipline is marked with a cross)
- Uppdrag nr
- Ritad/konstr av
- Handläggare
- Datum
- Ansvarig
- Type of work (e.g. NYBYGGNAD, OMBYGGNAD)
- Content (e.g. PLAN 1, DEL 2, VVS-INSTALLATIONER)
- Skala
- Nummer
- Bet (ändringsbeteckning)

## Level and reference abbreviations

| Code | Swedish | English |
|---|---|---|
| BEF | Befintlig | Existing |
| VG | Vattengång | Invert level (water line of a gravity pipe) |
| CL | Centrumlinje | Centre line |
| FG | Färdigt golv | Finished floor level |
| ÖG | Över (färdigt) golv | Above finished floor level |
| ÖK | Överkant | Top edge / top of |
| UK | Underkant | Bottom edge / underside of |
| UT | Undertak | Suspended ceiling |
