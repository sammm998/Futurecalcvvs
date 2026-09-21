# Rörtyper på svenska VVS-ritningar

Två källor ligger bakom det här dokumentet, och de säger inte riktigt samma sak:

1. **Standarden och branschpraxis** — SS 32260 (symboler och beteckningar för VVS-installationer), SS 32271
   (linjetyper), ISO 4067-1 för det internationella, samt kommunernas och regionernas egna beteckningssystem
   (Göteborgs RA-1865, Region Skånes VVS-SÖ märkstandard, Locums och Micasas märkanvisningar).
2. **Vad ritningarna faktiskt gör** — en räkning över stilbibliotekets 35 ritningar, där motorn läst varje sidas
   egen beteckningslista. 120 skilda koder, från sju olika projekterande kontor.

Skillnaden mellan de två är hela poängen: standarden ger formen, men **varje ritning definierar sin egen
vokabulär i beteckningslistan uppe till höger**, och det är den som gäller. Det är därför motorn läser listan
först och aldrig antar en kodlista.

---

## 1. Hur en beteckning är uppbyggd

Alla kontor i biblioteket följer samma grundform, med olika separatorer:

```
SYSTEM + löpnummer  –  MATERIAL  –  DIMENSION  [ / ISOLERING ]

VS11 - S13 - 42 - F100      värme sekundär ventilation, stålrör pressfog, DN42, 100 mm isolering
S1   - P5  - 110            spillvatten, PP ljuddämpat, DN110
KV01 - X7  - 25 - W40       tappkallvatten, PAL raka rör, DN25, mineralull diffusionstät 40 mm
RAD2 - S13 - 35 / W         värme radiatorer, stålrör, DN35, mineralull med alu-plåt
DBA1 - 110                  bräddavlopp, DN110 (material underförstått)
```

Ett annat kontor skriver samma sak med dimensionen på **raden under koden**, understruken:

```
S12          S1-G3
───          ─────
110          75 (L)
```

Båda formerna betyder samma sak, och motorn viker in dimensionsraden i namnet så att de ger **en** identitet.

---

## 2. Systemen — vad som faktiskt förekommer

Kolumnen "ark" är antalet ark i biblioteket där koden lästes ur sidans egen lista.

### Tappvatten

| kod | ark | betydelse | hur den ritas |
|---|---|---|---|
| `KV`, `KV1`, `KV01`, `KV02` | 15 | Tappkallvatten (KV02 = t.ex. kombiugn, egen krets) | tunn heldragen, ofta i knippe med VV/VVC |
| `VV`, `VV1`, `VV01` | 28 | Tappvarmvatten (55 °C) | samma penna som KV, parallell |
| `VVC`, `VVC1`, `VVC01` | 15 | Varmvattencirkulation | tredje linjen i knippet, klenaste dimension |

Tappvatten går nästan alltid som **knippe av 2–3 parallella linjer** med en staplad etikett som listar dem i
den ordning de korsas. Dimensioner 12–63 mm.

### Spillvatten och avlopp

| kod | ark | betydelse |
|---|---|---|
| `S`, `S1`, `S01` | 25 | Spillvatten allmänt (fall min. 1 %) |
| `S2` | 6 | Spillvatten oljebemängd |
| `S3`, `SF01` | 22 | Spillvatten till fettavskiljare (fall min. 2 %) |
| `S3L`, `SLV` | 10 | Spillvattenluftning / ventilation |
| `D`, `DBA` | 18 | Dagvatten, bräddavlopp |
| `DR1` | — | Dränering |

Självfallsledningar: **grövre penna än tappvattnet**, dimensioner 32/40/50/75/110/160. Ritas i eller under golv
och därför oftast **streckade eller streckprickade**.

### Värme och kyla

| kod | ark | betydelse |
|---|---|---|
| `VP1`, `VP01` | 22 | Värmebärare primär (t.ex. 100–25 °C) |
| `VS1`, `VS11`, `VS21`, `VS31` | 25 | Värmebärare sekundär — ventilation / radiatorer / golvvärme, med temperaturpar i listan |
| `RAD1`, `RAD2`, `RAD3` | 14 | Värme sekundär, radiatorer respektive luftvärme |
| `FJV1` | — | Fjärrvärme |
| `KB`, `KM` | — | Köldbärare och kylsystem |

Fram- och returledning går parvis. Värmerör är **nästan alltid isolerade**, vilket syns i beteckningens sista
led (`F50`, `F60`, `W40`).

### Övriga medier

`SP` sprinkler, `G`/`G2`/`G3`/`G6`/`G75` gas och gasflopp, `L1`/`L3` andningsluft och instrumentluft, `TA`
tryckluft, `O` olja, `MG` medicinska gaser. Dessa förekommer på sjukhus- och industriark och har egen linjetyp
per system, alltid definierad i sidans egen lista.

---

## 3. Materialkoderna — det andra ledet

Det här ledet är det som skiljer kontoren mest åt, och det är läst direkt ur ritningarnas listor:

| kod | ark | material |
|---|---|---|
| `X7` | 12 | PAL, raka rör |
| `X31` | 5 | PEX-rör |
| `X32` | 5 | PEX-rör, extraisolerade |
| `X72` | — | PAL med rör |
| `S13` | 12 | Stålrör, elförzinkade, pressfog |
| `S6` | 5 | Tryckkärlsstål |
| `P2` | 12 | PP-rör, lämpade för ingjutning |
| `P3` | 12 | PP-rör, släta markavloppsrör |
| `P5` | 5 | PP-rör, avlopp inomhus, ljuddämpat |
| `G3` | 12 | Gjutjärn, MA-avloppssystem |
| `E10` | 7 | PEH-rör, prefab avlopp |
| `E13` | — | PEM tryckrör, slang |
| `K5` | 5 | Kopparrör, förkromat |
| `R2`, `R10` | — | Syrafast stål, rostfritt avloppsrör muff |

Ett kontor använder i stället **rena siffror** som materialled: `8` MPF-rör, `21` LK-PAL, `22` PEX typ LK
Universal-RIR, `26` Uponor Ecoflex Thermo Twin, `27` Ecoflex Aqua, `29` LK-PAL Universal-RIR+isol, `50`
markavloppsrör, `51` PP-rör. Det är precis den sortens variation som gör att en fast kodlista inte fungerar.

### Isolering, sista ledet

`W` mineralull fabriksmonterad alu-plåt · `B` aluminiumplåt / rörskål mineralull · `C` plastplåt ·
`F50`/`F60`/`F80`/`F100` tjocklek i mm · `-F` "ev. isolering".

---

## 4. Linjetyperna — var röret ligger, inte vilket system det är

Det här är den viktigaste insikten för mängdning, och den motsäger en vanlig förväntan. Enligt svensk ritstandard
säger **linjetypen var röret ligger i höjdled**, inte vilket system det är:

| linjetyp | betydelse |
|---|---|
| heldragen | över golv, synlig |
| streckad | i eller under golv |
| punktstreckad (streck-prick) | under tak |
| punkt-punkt-streckad | över takbjälklag |

Systemet skiljs i stället åt genom **beteckningen, pennbredden, färgen och lagret**. Konsekvens för motorn: en
och samma streckprickade penna kan bära flera system, och ett och samma system kan byta linjetyp när det går
från golv till tak. Därför grupperas geometri på (lager, pennbredd, färg) — inte på streckmönster — och
identiteten kommer alltid från etiketten.

Streckmönstret är däremot användbart som *struktur*: en dash-dot-linje har två olika mellanrum i sitt mönster
(streck→prick och prick→streck), vilket är varför brygglogiken måste hantera flera gapstorlekar i samma familj.

---

## 5. Vad det betyder för hur motorn läser

| observation | följd i koden |
|---|---|
| Varje ritning definierar sin egen vokabulär i beteckningslistan | listan läses först, per sida; koder klassas som system / objekt / material efter hur ritningen använder dem |
| Systemkoden kan skrivas `KV`, `KV1`, `KV01`, `KV02` | lagernamn matchas efter hur exakt de namnger systemet — `KV02` slår `KV` |
| Materialledet varierar mellan kontor och kan vara siffror | grammatiken lärs per ritning, ingen fast kodlista |
| Dimensionen kan stå inline eller på raden under | båda formerna viks in i samma identitet |
| Linjetypen betyder höjdläge, inte system | familjer på (lager, penna, färg); identitet endast via etikett |
| Tappvatten går i knippe med staplad etikett | flera rader mot flera parallella rör — löses via lagernamn, annars redovisas det som ouppklarat |
| Isoleringsledet hör till dimensionen | en kort bokstavssvans efter måttet delar inte ett rör i två |

---

## Källor

- [Rörledningar – symboler och beteckningar, Byggipedia](https://byggipedia.se/ritningslasning/installationsritningar/rorledningar-symboler-och-beteckningar/)
- [Linjer, symboler och förkortningar, Byggipedia](https://byggipedia.se/ritningslasning/om-bygghandlingar/linjer-symboler-och-forkortningar/)
- [SS 32260 – Byggritningar, installationer: symboler och beteckningar för VVS, SIS](https://www.sis.se/en/produkter/standardization/technical-drawings/construction-drawings/ss32260/)
- [ISO 4067-1:1984 – Technical drawings, installations: graphical symbols for plumbing, heating, ventilation](https://www.iso.org/standard/9778.html)
- [RA-1865 Beteckningssystem för VVS- och SRÖ-installationer, Göteborgs stad](https://goteborg.se/wps/wcm/connect/f4e58909-d650-4515-95a4-4c475bf567b2/RA-1865-v.17.0+Beteckningssystem+f%C3%B6r+VVS-+och+SR%C3%96-installationer_2026.pdf?MOD=AJPERES)
- [RA-1855 Beteckning, märkning och skyltning, Göteborgs stad](https://goteborg.se/wps/wcm/connect/69001a32-2304-4467-844e-f0f0169c7963/RA-1855-v.5.0_Beteckning,_m%C3%A4rkning_och_skyltning.pdf?MOD=AJPERES)
- [Märkstandard Textdel VVS-SÖ, Region Skåne](https://www.skane.se/dokument/83881233)
- [Märkbilaga beteckningar VA-, VVS-, kyl- och processmediesystem, Locum](https://www.locum.se/globalassets/global/3.-verktygen/styrdokument-fastigheter/tekniska-anvisningar/5.-va-vvs-kyl-och-processmediesystem/bilaga-markning.pdf)
- [Vad betyder strecken på en VVS-ritning?, Nordic Industry](https://nordicindustry.net/vvs-ritning-streck/)
- [Plumbing drawing, Wikipedia](https://en.wikipedia.org/wiki/Plumbing_drawing)
- Primärkälla för sifferkolumnen "ark": stilbibliotekets 35 ritningar, beteckningslistorna lästa av motorn
  (`results/validation/styles/corpus.md`).
