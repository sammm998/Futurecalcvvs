# Starta VVS-systemet

Öppna **http://127.0.0.1:8765** när servern körs. Starta annars genom att dubbelklicka
på `Starta-VVS.command` i den här mappen. Låt terminalfönstret vara öppet.

1. Skapa ditt lokala konto. Det första kontot blir administratör. Alla konton i lokalläget kan analysera utan credits.
2. Skapa ett projekt och välj en eller flera PDF-filer. Identiska filer i samma projekt återanvänds.
3. Välj ritningarna och tryck **Analysera valda**. Resultaten sparas även om webbläsaren stängs.
4. Öppna analysen. Kontrollera skala, rörmarkeringar, dimensioner och kvalitetsbesked.
   Under **Översikt** visas också avlästa standardangivelser och jämförelse med eventuella längdmarkeringar.
   Under **Förklaringslista** finns en sökbar svensk VVS-kodreferens.
5. Granska tvetydiga sträckor och använd rättelser/manuell mängdning när det behövs.
6. Exportera mängderna som Excel, CSV, JSON eller markerad PDF. Kontrollera våningshöjd och
   inställningen för skrafferade ytor före export.

## Installation på en annan dator

Python 3.11 eller senare och Node.js/npm behövs. Kör i systemmappen:

```sh
./setup-local.sh
./Starta-VVS.command
```

Kärnanalysen körs lokalt. Startskriptet stänger av molnläsare och OCR som standard.
Extra OCR kan installeras med `.venv/bin/python -m pip install -r backend/requirements-ocr.txt`.
Versionen använder RapidOCR 3 med stöd för Python 3.13 och latinska tecken. Aktivera
**Administration → Teckenhjälp** för att använda den i nya analyser. Första gången hämtas
cirka 10 MB offentliga modellfiler; bildläsningen sker sedan lokalt. Ritningarna skickas
inte till modellservern. Modellerna sparas i `.local/ocr-models/` och kan återanvändas offline.
OCR är en hjälp för text på vektorritningar och ger inte stöd för automatisk mängdning av skannade blad.
Etikettmodellen från PipeStudio kan installeras med motsvarande `backend/requirements-ml.txt`
och aktiveras med `VVS_LABEL_AUDIT=true`. Den ger granskningsförslag, inte egna rörmängder.

## Dina data

Databas, uppladdningar och inloggningsnyckel ligger i `.local/`. Säkerhetskopiera den mappen
när servern är stoppad. Behåll `settings.json` tillsammans med databasen. Testinstallationer
ligger separat i `.local/qa*/`; de tillhör inte dina projekt. Originalritningarna i Downloads ändras inte.

## Analysens status

Systemet är en körbar lokal arbetsversion med VVS5:s gränssnitt, PipeStudio-referenser
och kodordlista från swedish-vvs-drawings.
Automatisk analys stöder vektor-PDF. Skannade blad, otydliga beteckningar, svåra dimensionsbyten och
rör utan entydiga hänvisningar kräver granskning eller manuell mängdning.

**Klar analys betyder att körningen är färdig. Det betyder inte att varje rör är korrekt mängdat.**
Kvalitetsbeskedet visar täckning och interna kontroller; en kontroll mot handmängdning är separat.
Alla 787 unika PDF-innehåll är inventerade, men hela materialet är inte verifierat för obevakad mängdning.

Se [senaste leveransrapporten](docs/LEVERANS-2026-09-20.md) för ändringar, prov,
jämförelser mot referenslinjer och kvarvarande begränsningar.

Fullständig källimport och kvarvarande regelskillnader: [källgranskning 20 september](docs/KALLGRANSKNING-2026-09-20.md).
