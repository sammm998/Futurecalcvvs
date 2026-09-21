# TRUE HOLDOUT - läget, protokollet och kandidaterna

## Läget 2026-09-11

Holdout är **blockerat**. Alla 71 logiska blad som har både en ren PDF och en referens (facit-xlsx,
Bluebeam-XML, markerad PDF eller CVAT) ligger i `data/` och har varit med i tidigare körningar: de är
DEVELOPMENT. De 287 blad i ritningsmappen som aldrig öppnats av motorn har ingen referens alls.
Se `results/2026-09-11-topologi/corpus_inventory.md` §4-§6 och `corpus_pairing.csv` (kolumnen VALIDATION_SET).

Ett holdout-mått räknat på DEVELOPMENT-blad är inte ett holdout-mått, hur blint det än kördes: varje
generisk regel i motorn har tagits fram med de bladen i sikte. Det som mäts där är hur väl motorn läser
det den lärt sig läsa - och det redovisas som det, i grindkörningarna (`gate52-facit-metrics.md`).

## Kandidater, i ordning

| Mapp på Drive | Blad | Varför den duger | Vad som krävs |
|---|---:|---|---|
| Other drawings / Fyrens förskola | 21 | egen konsult, egen exportkedja: främmande stil | facit för minst 10 blad |
| Style of drawings / 12 | 13 | de 13 som inte speglas lokalt (resten är Priorn = DEVELOPMENT) | facit |
| Other drawings / Vinkelboda ombyggnad 2026 | 79 | utan seriebeteckning, annan namngivning | facit + ritningsnummer ur huvudet |
| Other drawings / Hyllie hybrid | 28 | annan konsult | facit |
| Other drawings / Axis | 247 | samma exportkedja som Rundstickan/set 3 | duger bara för generalisering *inom* stil, inte mellan stilar |

Facit produceras av en person i Bluebeam på samma sätt som set 1-3 (Ämne = beteckning, Längd i m, en rad per
mängdad sträcka) och läggs på Drive bredvid bladet. Den får inte kopieras in i `data/` förrän steg 3 nedan.

## Protokollet, i den ordning det måste ske

1. **Frys motorn.** `git rev-parse HEAD` skrivs ned; `results/<dag>/hashmanifest-holdout.json` byggs över
   `engine/vvs_engine` (samma verktyg som `hashmanifest-baseline.json`). Ingen ändring i motorn efter detta
   förrän mätningen är redovisad.
2. **Hasha bladet.** sha256 av den rena PDF:en innan den öppnas av motorn; hashen skrivs i körningens JSON
   (`engine/tools/gate_run.py` gör det: `input_sha256`).
3. **Kör blint.** `python3 engine/tools/gate_run.py results/<dag>/holdout01.json` på bladen - utan referens i
   `data/`, utan att någon tittat på facit. Frys utfallet: hasha JSON-filen.
4. **Först nu** läggs facit i `data/holdout_<namn>/facit.xlsx` och `engine/tools/facit_metrics.py` körs.
   Utfallet redovisas som HOLDOUT, per stil, med COVERAGE, FALSE_OWNERSHIP, DESIGNATION_RECALL/PRECISION och
   utsträckningsklasserna.
5. **Efter mätningen** är bladet DEVELOPMENT. Det får användas till rotorsaksanalys, men nästa holdout måste
   vara nytt material. Manifestet uppdateras (`corpus_manifest.py`, `corpus_verify.py`, `corpus_inventory.py`).

Det som aldrig får hända: att facit läses före steg 3, att en regel ändras mellan steg 1 och 4, eller att ett
blad som redan öppnats kallas holdout.

## Vad grinden kräver för att en ändring ska få stanna

Zero verified false ownerships och ≥ 95 % identitetsriktig rörutsträckning per stil, mätt på holdout - inte på
utvecklingskorpusen. Tills holdout finns är varje ACCEPT i loggen villkorad: den säger att ändringen inte
kostade något på det material motorn redan sett, och inget mer.
