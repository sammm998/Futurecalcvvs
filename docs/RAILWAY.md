# Drift på Railway

En behållare kör allt: motorn, API:t och den byggda webbappen, som API:t serverar självt. `Dockerfile` bygger
den och `railway.json` säger hur den startas och hälsokontrolleras.

    build:  DOCKERFILE, Dockerfile
    deploy: healthcheckPath /health, timeout 120 s, restart ON_FAILURE (max 5)

## 1. Tjänsten

* **Källa:** repot, grenen som ska driftsättas. Railway bygger `Dockerfile` i roten - ingen byggkommandorad
  behöver sättas.
* **Port:** `PORT` sätts av Railway och läses av startkommandot; ingenting att konfigurera.
* **Volym:** montera en volym på `/data`. Utan den ligger databasen och de uppladdade ritningarna i behållarens
  filsystem och försvinner vid varje driftsättning. Imagen pekar redan dit:
  `VVS_STORAGE_ROOT=/data/storage`, `VVS_DATABASE_URL=sqlite:////data/vvs.db`.
* **Hälsa:** `/health` svarar utan inloggning. `/api/version` säger vilken byggning som kör och vilka
  andraläsare som är konfigurerade.

## 2. Miljövariabler

Krävs:

| variabel | varför |
|---|---|
| `VVS_SECRET_KEY` | nyckeln varje inloggningsbevis undertecknas med. Tjänsten **vägrar starta** på källkodens standardvärde: ett bevis undertecknat med en publik sträng kan vem som helst skriva om till vilket konto som helst. Sätt en lång slumpsträng: `python -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `VVS_CORS_ORIGINS` | de ursprung webbappen anropar API:t från |

Bör sättas:

| variabel | förslag | vad den gör |
|---|---|---|
| `VVS_WORKER_THREADS` | `1` per vCPU | hur många blad som mäts samtidigt |
| `VVS_ANALYSIS_DEADLINE_S` | `1800` | tidsbudget per blad; utan den håller ett tätt blad arbetaren för alltid |
| `VVS_RUN_REVIEW` | `true` | agenterna prövar det färdiga resultatet |
| `VVS_REVIEW_OCR` | `true` | OCR som oberoende andra läsning av texten |
| `VVS_OCR_ASSIST` | `true` | OCR får namnge tecken streckigenkännaren inte kunde |
| `VVS_ALLOW_REGISTRATION` | efter behov | öppen eller stängd registrering |

Andraläsarna (se `docs/ARCHITECTURE.md`):

| variabel | vad den gör |
|---|---|
| `OPENAI_API_KEY` | ger Astra-läsaren |
| `ANTHROPIC_API_KEY` | ger Claude-läsaren |
| `VVS_SECOND_READERS` | `auto` (de som går att nå), `none`, `astra`, `claude` eller `astra,claude` |
| `VVS_SECOND_READER_MODEL` / `VVS_CLAUDE_MODEL` | modellnamn, om annat än standard |
| `VVS_SECOND_READER` | `false` stänger av dem helt oavsett nycklar |

**Är båda nycklarna satta frågas båda läsarna om varje öppet fall, och fallet avgörs bara när de väljer samma
kandidat.** Är de oense står det kvar som tvetydigt. Det är avsikten och det syns i resultatet.

Nycklarna sätts som variabler på tjänsten i Railway och hör aldrig hemma i en fil i repot. De läses ur miljön i
anropsögonblicket, läggs på tråden och skrivs aldrig ned, loggas aldrig och kommer aldrig tillbaka i ett
resultat. `/api/version` säger att en nyckel finns, aldrig vilken.

## 3. Kontrollera en driftsättning

```
curl -s https://<tjänsten>/health
curl -s https://<tjänsten>/api/version
```

`/api/version` ska visa byggningen och, under `second_reader`, varje läsare med `reachable` och `in_use` samt
`agreement_required`. Står `enabled: false` med ett skäl som nämner en saknad nyckel är panelen avstängd - då
mäter tjänsten på sin egen geometri och lämnar de öppna fallen öppna, vilket är korrekt men ger färre avgjorda
rader än en driftsättning med nycklar. Två driftsättningar som skiljer sig där ger olika mängder på samma
ritning, och det är därför talet står publikt.

`engine/tests/test_the_service_says_which_readers_may_answer.py` håller formen på det svaret.

## 4. Databasen, och varför den kan se tom ut

**Det vanligaste felet vid driftsättning här är att data ser ut att försvinna.** Imagen pekar på
`sqlite:////data/vvs.db`. Finns ingen volym monterad på `/data` skrivs databasen i behållarens eget filsystem,
och behållaren byts ut vid varje driftsättning. Ingenting kraschar, ingenting loggas, och gränssnittet ser
likadant ut - tomt. Lägger man till en Postgres-tjänst i Railway men inte pekar appen på den händer samma sak:
databasen finns, är tom, och appen tittar aldrig åt dess håll.

Två uppsättningar fungerar:

1. **Volym.** Montera en volym på `/data`. Då ligger både SQLite-filen och de uppladdade ritningarna på den, och
   de överlever en driftsättning. SQLite körs i WAL-läge med väntetid och räcker långt.
2. **Egen databastjänst.** Lägg till Postgres i projektet. Railway sätter då `DATABASE_URL` på tjänsten, och
   appen tar den automatiskt om `VVS_DATABASE_URL` inte är satt - den gamla `postgres://`-formen översätts till
   drivrutinen SQLAlchemy vill ha. **Ritningsfilerna ligger fortfarande på disk**, så en volym på
   `VVS_STORAGE_ROOT` behövs ändå, eller ett objektlager.

Tjänsten säger själv vad som gäller. Vid varje uppstart skriver den en rad i loggen:

```
[data] OK: postgresql som egen tjänst: data ligger utanför behållaren
[data] rader: {'users': 12, 'projects': 4, 'drawings': 31, 'jobs': 33}
```

...eller, när något är fel:

```
[data] FLYKTIG: ligger i behållarens eget filsystem och försvinner vid nästa driftsättning: databasen
       (/data/vvs.db) och ritningarna (/data/storage). Montera en volym på katalogen, eller lägg till en
       databastjänst och peka VVS_DATABASE_URL på den.
```

Samma besked ligger i `/api/version` under `data`, med `persistent` (`true`/`false`/`null`), skälet i klartext,
var filerna ligger, och hur många rader tjänsten faktiskt har. Ingen anslutningssträng, ingen användare och
inget lösenord lämnar tjänsten - bara sorten, värden och databasnamnet.

    curl -s https://<tjänsten>/api/version | python3 -m json.tool | head -40

`engine/tests/test_the_service_says_where_its_data_lives.py` håller formen på det svaret.
