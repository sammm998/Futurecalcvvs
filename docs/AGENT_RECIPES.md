# Från agentens lösning till regel för alla ritningar

Det agenten lär sig ska komma alla till del. Ett fel från en ritning får ändå inte spridas till andra. Därför går
en lösning genom samma steg varje gång:

```
agenten löser → recept (delas med alla konton) → agenten skriver det som en regel → regelkandidat
  → spärren mot kontrollerade ritningar → admin aktiverar → regeln körs på varje läsning, även utan AI
  → stängs av automatiskt om användare ångrar den för ofta
```

## 1. Agenten löser ett problem

Agenten tar ett öppet problem på en ritning, till exempel en beteckning utan rör, onamngivet rör, en flagga eller en
saknad skala. Den löser det med egen kod i sandlådan och skriver rättelser märkta `agent`, gult och till granskning.

## 2. Receptet sparas och delas med alla konton

Det som fungerade sparas som ett recept (`agent_recipes`): problemtyperna, koden, verktygen i ordning och
rättelserna. Recepten visas för agenten på **alla konton**. Det var tidigare per konto, av två skäl: en ritningsstil
kunde vilseleda tolkningen av ett annat kontors ritningar, och kundernas ritningar får inte läcka mellan konton.
Så hanteras det nu:

- **Bara metoden delas.** Ett annat konto får koden och verktygsordningen, men inte problemtexterna eller rapporten.
  Kommentarer i koden och strängar längre än 40 tecken tas bort.
- **Utfallet avgör.** Varje gång ett recept visats och agenten skrivit rättelser räknas det som ett försök. Ett
  försök håller om rättelserna står kvar. Rättelser som lagts åt sidan för att ritningen lästs om räknas som
  kvar.
- **Dåliga recept visas inte.** Ett recept som hållit i under 60 % av minst 3 försök visas inte längre. Recepten
  sorteras efter hur ofta de hållit, på hur många konton och hur ofta de använts. Agenten får högst 5 recept.
  Ritningen avgör alltid.

## 3. Agenten skriver lösningen som en regel

Efter att ha löst ett problem kan agenten anropa `foresla_regel(kod, problemtyp, beskrivning)` med en funktion:

```python
def regel(problem, blad):          # problem: typ, text, bbox, beteckning, plats
    return [{"gor": "rita", "segment_id": [...], "beteckning": "..."},
            {"gor": "byt_beteckning", "ror_id": [...], "beteckning": "..."},
            {"gor": "radera", "ror_id": [...]},
            {"gor": "skala", "matningar": [{"a": [x, y], "b": [x, y], "mm": n}]}]
```

`blad` innehåller bladets linjer (`segs`), texter, rörbitar, läsningens rör (`ror`) och skalan (`mpp`).

**En regel mäter aldrig själv.** Koden körs i sandlådan och namnger bara åtgärder. Varje åtgärd går genom samma
verktyg som agenten använder:

- metrarna mäts från linjer som finns på bladet
- beteckningar som bladet inte skriver avvisas, liksom skalor som ingen plan ritas i
- en regel får göra högst 60 åtgärder per blad och lägga till högst 30 % av bladets egna meter

**Kandidat.** Funktionen sparas som kandidat (`learned_rules`, läget `kandidat`) bara om den på sitt eget blad gör
det agenten gjorde: samma typ av rättelse, samma beteckning, metrarna inom 20 % och inget mer. Annars får agenten
veta skillnaden och kan rätta funktionen. Högst 3 regler per blad.

## 4. Spärren mot kontrollerade ritningar

Repot är publikt, så facit kan inte ligga där. Spärrens facit är i stället ritningar som kunderna själva har rättat
och markerat med **"Markera mängden som kontrollerad"** i analysvyn. Det sparar den rättade mängden per beteckning
(`confirmed_takeoffs`). Markeringen kan ångras, och den senaste per ritning och sida gäller. Körningar som har en
kontrollerad mängd raderas inte när disken städas.

För varje kontrollerat blad, i alla konton, räknas tre mängder:

- **före:** läsningens egen mängd
- **efter:** samma mängd med regelns rättelser
- **sant:** den kontrollerade mängden

Felet är summan av |meter − sant| per beteckning. Ett blad blir:

- **bättre** om felet minskar med mer än 0,2 m
- **sämre** om felet ökar med mer än 0,5 m, eller om någon beteckning blir mer än 0,5 m sämre

**Regeln klarar spärren** om inget blad blir sämre och regeln är bevisad. Bevisad betyder att den är bättre på minst
ett kontrollerat blad, eller att receptet bakom den har hållit på minst 3 ritningar från minst 2 konton.

**När spärren körs:** i en egen bakgrundskö när en kandidat skapas, när en ritning markeras som kontrollerad (för
alla kandidater och aktiva regler) och när en admin trycker "Kör spärren". En aktiv regel som gör ett nytt
kontrollerat blad sämre stängs av direkt.

## 5. Admin aktiverar

Under **Admin → Lärda regler** syns för varje regel:

- läget och problemtypen
- spärrens resultat per blad, med före, efter och utfall
- hur ofta den använts och ångrats
- koden

Knappen **Aktivera** fungerar bara när regeln har klarat spärren. Först då gäller regeln alla. Admin kan också stänga
av en regel.

## 6. Regeln körs på varje läsning

När en läsning är klar körs de aktiva reglerna före agenten, utan någon språkmodell. Varje regel körs bara på blad
som har problem av dess typ.

- Rättelserna märks `regel: <namn>` och kan ångras som alla andra.
- Agenten får sedan bara de problem som ingen regel löste.
- Det reglerna gjorde på en tidigare läsning av samma ritning läggs åt sidan. Det agenten gjorde där läggs åt
  sidan när agenten körs igen eller när en regel har rättat den nya läsningen. Så räknas samma rör aldrig två
  gånger. Utan aktiva regler och utan AI står de tidigare rättelserna kvar, som förut.

**Automatisk avstängning:** om användarna ångrar minst 30 % av en regels rättelser, efter minst 5 tillämpningar,
stängs regeln av. Orsaken syns för admin.

## Motorns egna regler

Det här ändrar inte motorns egen läsning. En lärd regel arbetar på det läsningen lämnade öppet. När en lärd regel
visat sig bära kan en utvecklare skriva om den till motorkod. En sådan ändring mergas bara om
`python engine/tools/corpus.py run …` och `gate …` mot `engine/tests/data/corpus_baseline.json` visar att inget
blad blir sämre.
