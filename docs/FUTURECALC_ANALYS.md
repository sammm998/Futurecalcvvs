# FutureCalc — repositorieanalys före redesign och Academy

Läst ur koden, inte ur minnet. Allt nedan är verifierat mot filerna.

## Stack

| Lager | Vad som faktiskt finns |
|---|---|
| Frontend | React 18.3 + TypeScript 5.5, Vite 5.4, react-router-dom 6.26 (BrowserRouter) |
| Styling | **Ren CSS** i två filer: `src/styles.css` (165 kB, appen) och `src/landing.css` (92 kB, publika sidor). Ingen Tailwind, ingen CSS-in-JS, inget komponentbibliotek. |
| 3D | three.js 0.186 (`src/three/`, `Drawing3DView`, `BuildingView3D`) |
| PDF | pdfjs-dist 4.7 (`PdfViewer.tsx`, 57 kB) |
| Motion | Egenbyggt: `lp-smooth.ts` (lerp-scroll, parallax), `lp-motion.ts` (IntersectionObserver), `Reveal.tsx` (radmask), `ChapterBar.tsx`, `PageCurtain.tsx`, `FeatureFilm.tsx`. **Ingen GSAP, ingen Lenis, ingen Framer Motion.** |
| Backend | FastAPI + uvicorn, SQLAlchemy 2.0, Pydantic 2 |
| Databas | SQLite som standard (`VVS_DATABASE_URL`), psycopg finns för Postgres |
| Migrationer | **Ingen Alembic.** `init_db()` kör `Base.metadata.create_all` + `_add_missing_columns()`, en handskriven lista `(tabell, kolumn, DDL)` som körs vid uppstart. Nya tabeller skapas automatiskt; nya kolumner på gamla tabeller måste in i listan. |
| Auth | OAuth2 password flow (**formfält** `username`/`password`, inte JSON) → JWT via pyjwt. `current_user`, `current_admin`, `current_staff`. Bruteforce-spärr i `auth.py`. |
| Roller | `Role.MEMBER` / `PARTNER` / `ADMIN` på `users.role` |
| Motor | `engine/vvs_engine` (Python), installeras som paket, importeras av backend |
| Serving | Ett enda Docker-image: frontend byggs i `node:20-alpine`, kopieras till `/app/frontend/dist`, FastAPI serverar SPA:n |

## Befintliga routes

Publika: `/`, `/login`, `/dokumentation`, `/priser`, `/om-oss`, `/hur-det-funkar`, `/funktioner/:slug`, `/utbildning`, `/utbildning/:modul`, `/utbildning/:modul/:lektion`, `/kontakt`

Skyddade (`<Guard>` → token): `/projekt`, `/projects/:id`, `/projects/:id/analys`, `/drawings/:id`, `/jobs/:id`, `/jobs/:id/kalkyl`, `/mangda`, `/mangda/:id`, `/cad`, `/cad/:id`, `/lar`, `/lar/:modul`, `/lar/:modul/:lektion`, `/agent`, `/material`, `/credits`, `/admin`

## Databasmodeller som finns

`User`, `Account`, `Project`, `ProjectAnalysis`, `DocumentOverride`, `Drawing`, `AnalysisJob`, `Correction`, `RuleSetting`, `Partner`, `Payout`, `CrmNote`, `Content`, `Experiment`, `Event`, **`CourseProgress`**, `Calibration`, `DrawingViewport`, `CadSheet`, `Space`, `ToolPreset`, `ServiceSetting`, `Calculation`, `Markup`, `CreditEntry`, `CadRevision`, `ContactMessage`

## Befintlig utbildning — vad som återanvänds och vad som saknas

**Finns:**
- `src/learn.ts` (633 rader): `Module[]` med `Lesson[]`, blocktyper `p | ul | terms | note | fig`, en `Quiz` per lektion. **Riktigt svenskt VVS-innehåll**, inget platshållarmaterial.
- `components/`: `Learn.tsx`, `LearnExercises.tsx`, `LearnWizard.tsx`, `Lecture.tsx`, `Academy.tsx`, `AcademySection.tsx`, `LearnFigures.tsx`
- `backend/app/academy.py` (138 rader): `GET /api/academy/progress`, `PUT /api/academy/progress/{course}`, `GET /api/academy/awards`
- `CourseProgress`: `user_id`, `course`, `step`, `done_steps` (JSON), `completed`, `score`, `awards` (JSON)

**Saknas mot uppdraget:**
- Innehållet är hårdkodat i TypeScript, inte datadrivet från servern → ingen course builder möjlig
- Ingen `Exercise`-modell, inga försök (`attempts`), ingen tolerans, ingen poäng per övning
- Ingen övningsmotor: inga mängdningsövningar, ingen komponentmarkering, inga kalkylövningar
- Ingen sluttenta, inga `ExamAttempt`, ingen autospar
- Inga certifikat, ingen verifiering
- Ingen XP, inga nivåer, inga prerequisites/låsta moduler
- Ingen admin/course builder

## Ritningsmotor som ska återanvändas, inte dupliceras

- `PdfViewer.tsx` — pdf.js-rendering, zoom, pan
- `Markups.tsx` / `MarkupsList.tsx` — markeringar, polyline, mätning, undo
- `src/cad/` — ritverktyg, snap, lager
- `src/palette.ts` — `identityColor()`, en färg per beteckning (regeln gäller överallt)
- `src/three/pipeArt.ts` — rörmaterial och böjgeometri

Träningsritningarna byggs som **SVG** med en egen lätt motor (`TrainingDrawing`), eftersom övningsblad ska vara små, deterministiska och versionshanterbara i repot — men mätlogiken (polyline → meter, tolerans) delas.

## Beslut fattade

1. **GSAP 3.15 + ScrollTrigger + Lenis 1.3 läggs till.** npm-registret är nåbart. Den egna lerp-scrollen ersätts av Lenis; `Reveal.tsx` behålls som fallback för reducerad rörelse.
2. **Academy blir serverdriven.** Nya tabeller, innehållet seedas från strukturerad Python-data. `learn.ts`-innehållet migreras in som seed i stället för att kastas.
3. **Migrationer** följer husets sätt: nya tabeller via `create_all`, nya kolumner via `_ADDED_COLUMNS`. Ingen Alembic införs — det vore ett parallellt system.
4. **Rättning sker på servern.** Facit lämnar aldrig servern i tentaläge.
5. **Namnet blir FutureCalc** överallt (10 förekomster av det gamla namnet).
