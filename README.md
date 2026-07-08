# Immo — Aggregatore Annunci Immobiliari

Web app full-stack che aggrega, deduplica e confronta annunci immobiliari da
**6 portali** italiani, con vista lista, mappa interattiva con disegno del
perimetro di ricerca, tracciamento delle variazioni di prezzo e scansione
one-click dalla homepage.

## Funzionalità

### Aggregazione multi-portale
Scraping da **Immobiliare.it**, **Casa.it**, **Tecnocasa**, **RE/MAX**,
**Gabetti** e **Vistocasa**. Idealista è presente ma disabilitato di default
(DataDome blocca tutto). Ogni annuncio nuovo viene deduplicato cross-portale
(indirizzo, prezzo, superficie, coordinate, stanze) e il portale con priorità
più alta diventa canonical; gli altri restano attaccati come `listing_sources`.

### Snapshot immutabile + tracciamento prezzi
Il primo scraping registra il "fatto storico" dell'annuncio; run successivi
saltano il detail-fetch per gli ID già in DB (nessuna sovrascrittura di
titolo/descrizione/foto) ma leggono comunque il prezzo dalle pagine di ricerca
per rilevare variazioni. Se il prezzo cambia, `price_previous` e
`price_changed_at` vengono aggiornati e la UI mostra badge ↓ verde
(riduzione) o ↑ rosso (aumento) sulle card.

### Vista lista con filtri completi
`/search` — 10+ categorie di filtri collassabili (tipo, dove, tipologia,
prezzo, superficie, locali, bagni, piano, caratteristiche, classe energetica,
stato, fonte), toggle grid/list, sort esteso (data, prezzo, €/m², superficie),
selettore page-size 20/50/100, chip di filtri attivi rimovibili singolarmente.

### Mappa interattiva con disegno perimetro
`/map` — Leaflet + OSM in split-pane (lista scrollabile a sinistra, mappa a
destra). Pin custom con prezzo abbreviato. **Disegna area** un perimetro
cliccando i vertici → il backend filtra con point-in-polygon (ray-casting).
Il perimetro è serializzato in URL, condivisibile, e attivo anche dalla
vista lista con banner + chip di rimozione.

### Scansione one-click con toast persistente
Bottone "Aggiorna annunci" in homepage lancia lo scraper come processo
detached (sopravvive ai riavvii del backend). Il toast in basso a destra
mostra fase corrente (Ricerca → Elaborazione → OK), progress bar
aggregata cross-portale, ETA calcolato client-side, pill per-portale con
% individuale, warning se un worker si blocca >120s.

### Dettaglio annuncio
`/listing/[id]` — Galleria con planimetrie in primo piano (badge dedicato,
mini-marker "Plan" sui thumbnail), lightbox zoom, prezzo con badge di
variazione, mappa embed, elenco delle fonti dei portali, annunci simili.

### Confronto
`/compare?ids=a,b,c` — Tabella side-by-side fino a 3 annunci selezionati
via checkbox dalle card della vista lista.

## Stack

**Backend**: Python 3.12 · FastAPI · SQLAlchemy 2.0 async · SQLite (WAL) ·
`curl_cffi` (Chrome TLS impersonation) · BeautifulSoup4 · lxml.

**Frontend**: Next.js 15 (Turbopack) · React 19 · TypeScript · Tailwind 4 ·
React Query · **nuqs** (URL state) · **Leaflet + react-leaflet** · lucide-react
· next-themes.

**Storage**: SQLite in `data/immo.db` (WAL mode per letture concorrenti). Path
migratorio a PostgreSQL previsto via SQLAlchemy — nessun raw SQL SQLite-only
tranne un `PRAGMA` e alcuni CAST in `_apply_listing_filters` per il floor.

## Quick start

### 1. Configurazione

```powershell
cd C:\Users\giuli\Documents\Progetti\immo
cp .env.example .env
```

Il `.env` alla root controlla il backend (portali abilitati, città default,
rate-limit). Il default della città è `bari` — cambialo se scrappi altre città.

Per il frontend, opzionalmente crea `frontend/.env.local`:

```
NEXT_PUBLIC_API_URL=http://localhost:8001
```

(Necessario solo se il backend non è sulla porta 8000. Usiamo 8001 in dev per
evitare conflitti con altri progetti locali.)

### 2. Installazione

```powershell
# Backend (Python 3.12+)
cd backend
pip install -e ".[dev]"

# Frontend (Node 20+)
cd ..\frontend
npm install
```

### 3. Avvio

```powershell
# Terminale 1 — Backend
cd backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload
```

```powershell
# Terminale 2 — Frontend
cd frontend
npm run dev
```

Apri **http://localhost:3000** e clicca **"Aggiorna annunci"** in homepage per
lanciare il primo scraping — oppure vai avanti col comando manuale sotto.

### 4. Scraping via CLI (alternativa al bottone UI)

```powershell
# Tutti i portali abilitati sulla città default (bari)
cd backend
python -m scraper.runner

# Un solo portale
python -m scraper.runner --portal vistocasa

# Città custom
python -m scraper.runner --city milano
```

### 5. Docker (alternativa)

```powershell
docker-compose up
```

## URL & pagine

| URL | Descrizione |
|-----|-------------|
| http://localhost:3000/ | Homepage con hero animato + bottone scan |
| http://localhost:3000/search | Lista con filtri, sort esteso, page-size |
| http://localhost:3000/map | Mappa + lista scrollabile + disegno perimetro |
| http://localhost:3000/listing/{id} | Dettaglio con planimetrie e price-history |
| http://localhost:3000/compare?ids=... | Confronto side-by-side fino a 3 |
| http://localhost:8001/docs | Swagger UI del backend |

## Come funziona (guida all'uso)

Questa sezione descrive **cosa succede** quando l'utente interagisce con l'app —
il flusso end-to-end tra scraper, DB, API e UI. Utile sia per l'utente finale
che per capire in che punto della catena intervenire quando qualcosa non torna.

### Il ciclo di vita di un annuncio

```
Portale web  ──┐
               ▼
      [Spider] scarica search page + detail page
               ▼
      [ListingItem] dataclass tipizzato
               ▼
      [Pipeline] dedup + upsert + price-diff
               ▼
      [SQLite]  Listing (canonical) + ListingSource[] (repliche)
               ▼
      [FastAPI] endpoint filtrano/proiettano su richiesta
               ▼
      [React Query] cache-and-refetch nel browser
               ▼
      [Pagine Next.js] mostrano lista/mappa/dettaglio
```

Ogni annuncio è **1 riga in `listings`** (il canonical) più N righe in
`listing_sources` (una per portale che lo pubblica). Se `immobiliare.it` e
`casa.it` hanno lo stesso appartamento, la riga canonical è del portale con
priorità più alta e l'altra si "attacca" come source — nella UI vedi il
badge "N fonti" sulla card.

### Prima esecuzione (DB vuoto)

Dopo `npm run dev` e `uvicorn`, `data/immo.db` è vuoto: `/search` mostra
"Nessun risultato". Serve popolare — due modi:

1. **Bottone "Aggiorna annunci" in homepage** (consigliato). Un click →
   lancio subprocess → toast in basso a destra segue il progresso.
2. **CLI**: `python -m scraper.runner --city bari` dalla cartella `backend`.
   Scrive gli stessi record; il toast **non** compare perché il polling è
   basato solo sull'endpoint status (che comunque risponde correttamente).

Il primo scrape su Bari dura ~30-40 min (~7000 listings totali). Immobiliare
è il più lento in fase search, casa.it è il più lento in fase fetch per via
del rate-limit conservativo (60 req/min).

### La scansione one-click, passo per passo

1. Utente clicca **"Aggiorna annunci"** in homepage → `POST /api/scrape/trigger`
2. Il backend lancia `python -m scraper.runner` come **processo detached** e
   ritorna `202 Accepted` immediatamente (nessun blocking)
3. Il processo scraper crea un `job_id` UUID e stampa una `ScrapeRun` per
   ogni portale abilitato, tutte con lo stesso `job_id`
4. Dentro `run_spider`, un **ticker asincrono** ogni 2s copia lo stato del
   `_ProgressBar` (fase, done, total) sulla riga DB
5. Il **frontend** ha già mostrato il toast in `optimistic` mode; da quando
   il polling di `useScrapeStatus` intercetta `is_running=true` (entro 500ms
   grazie al burst di invalidation), inizia il polling a 2s
6. `GET /api/scrape/status` filtra le `ScrapeRun` per `job_id` più recente
   e restituisce un aggregato con `progress_done` / `progress_total` sommati
7. Il toast calcola l'ETA client-side: `elapsed × remaining / done` (o
   fallback a "1 sec/item" nei primi secondi)
8. Al termine, `phase` diventa `done`, il toast si tinge di verde con il
   riepilogo "N nuovi · M trovati" e auto-dismiss dopo 30s

Se il backend crasha o viene riavviato durante lo scan, il subprocess
**sopravvive** perché è staccato dal parent. Il toast resta accurato appena
il backend riparte.

### La ricerca su `/search`

- **Filtri collassabili** in sidebar (10+ sezioni). Ogni scelta aggiorna
  un query param via **nuqs**, immediatamente visibile in URL. React Query
  detecta il cambio di key → refetch.
- I filtri attivi diventano **chip** sopra la lista, con X singola. Un
  filtro rimosso re-esegue subito la ricerca senza toccare gli altri.
- **Sort** (dropdown): data recente / prezzo asc/desc / €/m² asc/desc /
  superficie. Tutti mappati a `ORDER BY` con `NULLS LAST`.
- **Page size** (20/50/100) — utile per rivedere velocemente tante schede.
  Cambiare il size riporta a pagina 1.
- **Toggle grid/list** (icone in ResultsHeader): grid = card con foto
  aspect-ratio 4:3; list = riga orizzontale con anteprima descrizione.
- **Bottone "Mappa"** accanto ai selettori → naviga a `/map`
  preservando *tutti* i filtri via `Header.PRESERVED_PARAMS`.

### La mappa con disegno del perimetro

- Split-pane: **lista scrollabile a sinistra** (200-2000 marker, tagliata
  a `limit`), **mappa Leaflet+OSM a destra**. Ogni pin è un `divIcon`
  custom con prezzo abbreviato (`€250k`).
- Hover su una card della lista → il pin corrispondente si evidenzia
  (bordo scuro, z-index alto). Click su un pin → apre popup + scroll
  della lista al listing.
- **Pan/zoom** della mappa → `moveend` emette il bbox della viewport →
  refetch dei marker filtrati sull'area visibile.
- **Bottone "Disegna area"** (icona matita) →
  1. Cursore diventa crosshair, viewport-sync in pausa
  2. Ogni click sulla mappa aggiunge un vertice (dot + polyline
     tratteggiata blu)
  3. **Invio** o **Termina (N)** chiude il polygon (richiede N≥3)
  4. **Esc** o **Annulla** esce senza salvare
- Il polygon finalizzato viene serializzato come
  `polygon=lat,lng;lat,lng;...` in URL. Backend fa: `polygon.bbox()` come
  pre-filtro SQL (indicizzato), poi point-in-polygon Python per il
  refinement esatto.
- Il perimetro è **preservato** navigando a `/search`: la lista mostra
  banner blu "Area disegnata attiva" + chip "Area disegnata (N pt)"
  nella barra dei filtri, con X per rimuoverlo.

### Il badge variazione prezzo

Quando lo scraper trova un listing conosciuto e il **prezzo sulla search
page** è diverso da quello in DB (tolleranza €1 per evitare jitter di
arrotondamento), aggiorna: `price` = nuovo, `price_previous` = vecchio,
`price_changed_at` = adesso. Il `PriceChangeBadge` calcola il delta % e
mostra:

- **↓ verde** con % negativa e prezzo precedente strikethrough se
  ridotto (l'evento più utile per un cercatore)
- **↑ rosso** con % positiva se aumentato
- Tooltip: "Variato N giorni fa · prima €X"

Il badge appare su ListingCard grid, ListingCard list e nell'header del
dettaglio.

### Planimetrie in galleria dettaglio

Sul dettaglio, le planimetrie (`floor_plans[]`, array separato dagli
`images[]`) vengono **prependute** all'array della galleria:

```tsx
const images = [...floorPlans, ...photos];
```

Sull'immagine corrente compare un badge **"Planimetria N/M"** quando è
una planimetria; sui thumbnail un mini-marker **"Plan"** in alto. Se
l'utente è su una foto e ci sono planimetrie, il badge diventa CTA
"Vai alla planimetria" → scroll del carousel a index 0.

### Confronto multi-annuncio

Da qualsiasi card della lista, un **checkbox** aggiunge il listing al set
`compareIds` (state locale, max 3). Quando `size ≥ 2` compare un floating
button "Confronta (N)". Click → naviga a `/compare?ids=a,b,c` che fa 3
query React Query in parallelo e renderizza una tabella side-by-side con
tutte le proprietà (prezzo, superficie, locali, classe energetica,
caratteristiche booleane con ✓/✗).

### Refresh mentale del flusso

Se qualcosa non funziona, chiediti in che punto della catena sei:

- **Non vedo l'annuncio nella lista** → è nel DB? (`sqlite3 data/immo.db
  "SELECT COUNT(*) FROM listings WHERE ..."`). Se sì è un problema API/UI;
  se no è un problema scraper.
- **Il toast non appare mai** → `GET /api/scrape/status` risponde? La
  scan sta scrivendo `ScrapeRun` rows? (`SELECT * FROM scrape_runs ORDER
  BY started_at DESC LIMIT 5`)
- **Il polygon non filtra** → la stringa `polygon` è ben formata in URL?
  (`lat,lng;lat,lng;...` con almeno 3 vertici) — se torna null il backend
  fa fall-through al filtro senza polygon.
- **Il prezzo non aggiorna** → lo spider ha implementato
  `parse_search_results_with_prices`? (solo immobiliare, casa e vistocasa
  la override).

## API principali

| Endpoint | Descrizione |
|----------|-------------|
| `GET /api/listings` | Ricerca paginata: 25+ query params (filtri, `polygon`, `bbox`, `sort`, `page_size`) |
| `GET /api/listings/{id}` | Dettaglio annuncio con tutte le `sources` |
| `GET /api/listings/{id}/similar` | Annunci simili (stesso portale/città/tipo) |
| `GET /api/listings/map` | Marker snelli per la mappa (max 2000, `polygon`+`bbox` supportati) |
| `GET /api/stats` | Contatori per portale/città, media €/m², ultime run |
| `POST /api/scrape/trigger` | Lancia scraping come subprocess (202 immediato) |
| `GET /api/scrape/status` | Aggregato del job più recente (progress, ETA, heartbeat) |
| `GET /api/scrape/runs` | Cronologia degli ultimi 20 run per debug |

## Architettura

```
backend/
  app/
    api/           Endpoint FastAPI (listings, scrape, stats)
    models/       SQLAlchemy: Listing, ListingSource, ScrapeRun, Favorite
    schemas/      Pydantic DTOs
    services/     Business logic (dedup, filtri, marker projection)
    utils/        Helpers (text norm, logging)
  scraper/
    spiders/      6 spider + BaseSpider abstract + PlaywrightSpider (idealista)
    utils/        Rate limiter, JSON-LD, agency parser, HTML extract
    pipeline.py   Dedup + upsert batch (SAVEPOINT per-item), price-diff
    runner.py     Orchestratore CLI + ticker async per il progress DB
    items.py      Dataclass ListingItem
frontend/
  src/app/
    page.tsx        Homepage con bottone scan e blob animati
    search/         Vista lista
    map/            Vista mappa con drawing perimetro
    listing/[id]/   Dettaglio con galleria planimetrie-first
    compare/        Confronto side-by-side
  src/components/
    listings/       Card grid/list, PriceChangeBadge
    search/         FilterFields (condiviso), FilterSidebar, ActiveFilters, ResultsHeader
    map/            MapView (react-leaflet), MapFilters (dropdown)
    scrape/         ScrapeProgressToast (persistente, mount globale)
    ui/             Badge, Skeleton, ImageLightbox
  src/hooks/        useListings, useScrapeStatus (polling adattivo)
  src/lib/          api client, types, utils di formattazione
```

## Deep dive per contributori

Le scelte non-ovvie del codice, per chi ci mette mano:

### Scraping — snapshot immutabile
Il pipeline (`scraper/pipeline.py`) usa `get_known_source_ids(portal)` per
sapere quali listing sono già in DB. La spider skippa la detail-fetch per
questi, e il pipeline si limita a bumpare `last_seen_at` e aggiornare
`price`/`price_previous` se il prezzo sulla search page è cambiato. Nessun
altro campo viene mai sovrascritto: la fotografia originale resta storicizzata.
Per forzare un re-fetch di un annuncio specifico: `DELETE FROM listings WHERE
source_id = ?` e rilancia lo scraper.

### Scraping — publication_date via CDN
Gabetti e Vistocasa non pubblicano date nell'HTML. Trucco: HEAD sulla prima
immagine del listing → `Last-Modified` del CDN riflette la data di upload
della foto, ottimo proxy per la data di pubblicazione. Vedi
`_pub_date_from_image()` in `gabetti.py` e `vistocasa.py`.

### Scraping — casa.it URL template
Le immagini di casa.it sono su
`https://images-1.casa.it/{size}/listing/{mediaid}`. Il segmento `/listing/`
è essenziale: senza, il CDN torna 400 "Invalid URI format". Documentato in
`casa.py:parse_listing` — facile da rompere se qualcuno cambia il template.

### Scraping — pagination ASP.NET (vistocasa)
Vistocasa è un WebForms puro con `__doPostBack` per la paginazione: la spider
override `run()` e fa GET → POST con `__EVENTTARGET=ctlNN` + `__VIEWSTATE`
rigenerato per pagina. Se il POST fallisce 3 volte di seguito, break early:
di solito significa che la sessione WebForms è morta.

### Backend — polygon filter
Il perimetro disegnato dall'utente (`polygon=lat,lng;lat,lng;...`) viene
usato come pre-filtro SQL sulla sua bounding box (indicizzata via `lat`/`lng`),
poi refinato in Python con ray-casting per il vero point-in-polygon. Per
~3000 righe è <5ms; se il DB cresce >100k considera PostGIS.

### Backend — scrape trigger come subprocess detached
`POST /api/scrape/trigger` **non** usa `BackgroundTasks` (morirebbero al
prossimo reload di uvicorn). Lancia invece `python -m scraper.runner` come
processo indipendente con `CREATE_NEW_PROCESS_GROUP | DETACHED_PROCESS`
(Windows). Il processo scrive sul DB condiviso via il ticker async, e
l'endpoint `/api/scrape/status` legge lo stato. Riavvii del backend non
interrompono lo scraping.

### Backend — aggregazione status via job_id
Ogni invocazione di `run_all_spiders` genera un `job_id` uuid; tutti i
`ScrapeRun` di quell'invocazione lo condividono. `/api/scrape/status`
filtra sul `job_id` del run più recente, isolando pulitamente il job in
corso da qualsiasi run precedente (anche orfani). Il clustering temporale
(usato prima) era fragile con job triggerati a pochi minuti di distanza.

### Backend — reporter `_phase` vs `_phase_key`
`_ProgressBar._phase` è il label italiano ("Ricerca"/"Elaborazione") per
il terminal. `_phase_key` è la chiave canonica (`search`/`fetch`/`done`/
`failed`) usata da DB e frontend. Sono due proprietà separate perché
servono a due consumatori con requisiti diversi.

### Frontend — nuqs come single source of truth
Ogni filtro (city, price_min, polygon, sort, page_size...) vive in URL
via `nuqs`. Nessun useState locale duplicato. Vantaggi: refresh conserva
lo stato, URL condivisibili, navigazione Search↔Map preserva i filtri
via `Header.PRESERVED_PARAMS`. Escluso di proposito il `bbox` (specifico
alla viewport della mappa) e il `page` (deve resettare a 1 quando cambi
filtro).

### Frontend — toast persistente non-sonner
`ScrapeProgressToast` è un componente React custom montato in
`RootLayout`, non un toast di libreria. Motivo: deve sopravvivere ai
route change e mostrare progress live via polling di `useScrapeStatus`
con interval adattivo (2s se running, 30s se idle). ETA a due tier:
`live_rate = done/elapsed` se abbiamo >=1s di dati, altrimenti baseline
"1 item/s".

## Configurazione (.env)

Solo i campi non-ovvi:

| Variabile | Default | Note |
|-----------|---------|------|
| `SCRAPE_DEFAULT_CITY` | `bari` | Città del run CLI e del bottone scan |
| `SCRAPE_IDEALISTA_ENABLED` | `false` | DataDome blocca — accendere solo con proxy residenziale |
| `SCRAPE_RATE_LIMIT_RPM` | 60 | Requests per minuto per dominio |
| `SCRAPE_CONCURRENCY` | 4 | Detail fetch concorrenti per spider |
| `DEDUP_THRESHOLD` | 0.85 | Score cross-portale per considerare due annunci uguali |
| `LISTING_INACTIVE_DAYS` | 14 | Dopo N giorni di silenzio → `is_active=False` |

## Deduplicazione — algoritmo

Score pesato in `app.services.dedup_service.find_duplicate`:

- **Indirizzo normalizzato**: 35%
- **Prezzo** (tolleranza ±10%): 20%
- **Superficie** (tolleranza ±10%): 20%
- **Geolocalizzazione** (distanza haversine): 15%
- **Numero stanze**: 10%

Soglia >= 0.85 per merge. Il portale con priorità più bassa (in
`PORTAL_PRIORITY = ["immobiliare", "casa", "tecnocasa", "gabetti", "remax",
"idealista"]`) resta canonical; gli altri diventano `ListingSource`. Se
arriva un match da un portale con priorità più alta, viene fatto un
`_promote_listing` che sovrascrive i campi canonical mantenendo `listing.id`
stabile.

## Troubleshooting

**"Il bottone Aggiorna annunci non fa nulla"** — Controlla nei log del
backend che la POST a `/api/scrape/trigger` sia arrivata. Poi verifica
il subprocess: `tasklist | findstr python`. Su Windows, se il subprocess
non parte, è quasi sempre un problema con `sys.executable` che punta a
un venv sbagliato.

**"Il toast dice `heartbeat 200s`"** — Lo scraper è bloccato (probabilmente
casa.it rate-limitato). Aspetta o killa il processo Python del runner.

**"Casa.it torna 400 sulle immagini"** — Controllo del template URL: dopo
la fix devono contenere `/listing/`. Se recente scraper ha salvato le
vecchie, DELETE i listing e re-scrappa.

**"Vistocasa non mostra planimetrie"** — Filtro `data-fancybox="planimetria"`
in BeautifulSoup può fallire se il sito cambia markup. Vedi
`vistocasa._extract_floor_plans()`.

## Test scraper

Nessun test unit ancora — solo smoke test manuale via:

```powershell
cd backend
python -c "
import asyncio
from scraper.spiders.vistocasa import VistocasaSpider
from scraper.spiders.base import SearchParams
from scraper.utils.rate_limiter import RateLimiter

async def main():
    sp = VistocasaSpider(rate_limiter=RateLimiter(requests_per_minute=120))
    async for item in sp.run(SearchParams(city='bari', max_pages=1)):
        print(item.title, item.price)
    await sp.close()

asyncio.run(main())
"
```

## Note di progetto

- **Path fissi Windows**: il progetto è configurato per un layout locale
  (`C:\Users\giuli\Documents\Progetti\immo`). Il `.env` alla root ha un
  `DATABASE_URL` assoluto; se cloni altrove, aggiornalo.
- **Il DB `data/immo.db` non è versionato**: gitignore lo esclude
  esplicitamente. Il primo scraping è necessario per popolarlo.
- **Backend porta 8001 in dev**: la porta 8000 è spesso occupata da altri
  progetti locali dello stesso autore. Cambia in `frontend/.env.local` se
  preferisci 8000.
