# Immo — Aggregatore Annunci Immobiliari

Web app full-stack che aggrega, deduplica e confronta annunci immobiliari da
**10 portali** italiani: ricerca full-text con filtri, mappa in stile portale
con anteprima rapida e disegno del perimetro, storico prezzi, aste,
preferiti, ricerche salvate con avvisi e scansione one-click dalla homepage.

## Funzionalità

### Aggregazione multi-portale
Scraping da **Immobiliare.it**, **Casa.it**, **Tecnocasa**, **RE/MAX**,
**Gabetti**, **Vistocasa**, **Wikicasa** (agenzie e aste giudiziarie),
**Subito** (dove pubblicano i privati), **Bakeca** e **TrovaCasa**. Idealista
è presente ma disabilitato di default (DataDome blocca tutto). Ogni annuncio nuovo viene deduplicato cross-portale
(indirizzo, prezzo, superficie, coordinate, stanze) e il portale con priorità
più alta diventa canonical; gli altri restano attaccati come `listing_sources`.
Gli annunci spariti da un portale vengono disattivati solo se l'ultima
scansione di quel portale ha visto **tutto** il catalogo della città (vedi
[Copertura](#scraping--copertura-e-disattivazione)).

### Snapshot immutabile + storico prezzi
Il primo scraping registra il "fatto storico" dell'annuncio; i run successivi
saltano il detail-fetch per gli ID già in DB (nessuna sovrascrittura di
titolo/descrizione/foto) ma leggono comunque il prezzo dalle pagine di ricerca
per rilevare variazioni. Ogni variazione finisce in `listing_price_history`:
le card mostrano il badge ↓ verde / ↑ rosso, il dettaglio il grafico dello
storico.

### Ricerca
`/search` — ricerca **full-text** (SQLite FTS5 con prefissi italiani:
"terrazz" trova terrazzo/terrazzi/terrazza), 10+ categorie di filtri
collassabili (tipo, dove, tipologia, prezzo, superficie, locali, bagni, piano,
caratteristiche, classe energetica, stato, fonte, **data di pubblicazione**,
**aste**), toggle grid/list, sort esteso, page-size 20/50/100, chip dei filtri
attivi rimovibili singolarmente. Ogni caratteristica (locali, superficie,
bagni, piano, ascensore, terrazzo, box…) ha la sua icona, uguale in tutta l'app.

### Mappa
`/map` — mappa **CARTO Voyager** in stile portale (OpenStreetMap se manca la
chiave, versione scura in dark mode), pin a pillola col prezzo, **cluster**
dei pin vicini, aste in arancione. A sinistra l'elenco: ogni riga mostra
portale, aste e da quanto è pubblicato; **cliccandola si apre un'anteprima**
(foto, dati principali, dotazioni, descrizione) ridimensionabile, con il link
alla scheda completa. I filtri si aprono in una sotto-barra chiudibile.
**Disegna area**: un perimetro cliccando i vertici → il backend filtra con
point-in-polygon; il perimetro è in URL, condivisibile, attivo anche in lista.

**Posizioni approssimate**: gli annunci senza coordinate (Subito, TrovaCasa,
agenzie che nascondono la posizione) ma con la via vengono messi sulla mappa
al centro della via, o al civico se c'è; il pin ha il bordo tratteggiato e
l'anteprima dice "posizione approssimativa". Chi indica solo la zona o il
comune resta fuori dalla mappa (ma è negli elenchi). Vedi
[Posizioni approssimate](#mappa--posizioni-approssimate).

### Aste
Gli annunci all'asta sono riconosciuti (dato strutturato su Immobiliare.it e
Wikicasa, analisi del testo sugli altri portali: "asta giudiziaria", "base
d'asta", "vendita senza incanto"…), segnalati con un'etichetta e filtrabili
(tutte / solo aste / escludi aste). Per le aste pubblicate su Wikicasa il
dettaglio mostra anche i dati della vendita: data e ora, prezzo base,
offerta minima e rilancio, termine per le offerte, tribunale e procedura,
il link per prenotare la visita sul Portale Vendite Pubbliche e i documenti
(avviso, delega). Arrivano anche quando l'annuncio principale viene da un
altro portale.

### Preferiti e ricerche salvate
Il cuore su card e dettaglio salva l'annuncio in `/favorites`. Una ricerca si
salva dalla lista; `/alerts` mostra per ognuna **cosa c'è di nuovo** dall'ultima
visita (annunci nuovi e ribassi). Opzionale: un'e-mail di riepilogo dopo ogni
scansione (SMTP).

### Scansione one-click
Il bottone "Aggiorna annunci" in homepage (con accanto la data dell'ultimo
aggiornamento) lancia lo scraper come processo detached, che sopravvive ai
riavvii del backend. Un toast persistente mostra fase, progress bar, ETA e
avanzamento per portale; su telefono occupa la larghezza ed è ridotto a una
riga. Scansioni periodiche automatiche: opt-in (`SCRAPE_SCHEDULE_ENABLED`).

### Dettaglio e confronto
`/listing/[id]` — galleria con planimetrie, lightbox accessibile, prezzo con
variazione e storico, dati con icone, mappa, fonti, annunci simili.
`/compare?ids=a,b,c` — tabella side-by-side fino a 3 annunci.

## Stack

**Backend**: Python 3.12 · FastAPI · SQLAlchemy 2.0 async · SQLite (WAL, FTS5)
· Alembic · `curl_cffi` (Chrome TLS impersonation) · BeautifulSoup4 · lxml ·
prometheus-client · sentry-sdk (opzionale).

**Frontend**: Next.js 15 (Turbopack) · React 19 · TypeScript · Tailwind 4 ·
React Query · **nuqs** (URL state) · **Leaflet + react-leaflet** + supercluster
· lucide-react · next-themes.

**Storage**: SQLite in `data/immo.db`. Lo schema è gestito da **Alembic**: le
migrazioni girano da sole all'avvio, precedute da un backup automatico in
`data/backups/` (ultimi 5).

## Quick start

### 1. Configurazione

```powershell
cp .env.example .env
cp frontend\.env.local.example frontend\.env.local
```

- `.env` (root) controlla il backend: portali abilitati, città di default
  (`bari`), rate-limit, avvisi e-mail, osservabilità. Vedi
  [Configurazione](#configurazione).
- `frontend/.env.local`: `NEXT_PUBLIC_API_URL` (il backend) e
  `NEXT_PUBLIC_CARTO_API_KEY`, la chiave gratuita delle mappe CARTO
  ([carto.com/basemaps/apikey](https://carto.com/basemaps/apikey)). Senza
  chiave la mappa usa OpenStreetMap.

### 2. Installazione

```powershell
# Backend (Python 3.12+)
cd backend
pip install -e ".[dev]"

# Frontend (Node 22)
cd ..\frontend
npm install
```

### 3. Avvio (sviluppo)

```powershell
# Terminale 1 — Backend
cd backend
python -m uvicorn app.main:app --port 8001 --reload
```

```powershell
# Terminale 2 — Frontend
cd frontend
npm run dev
```

Apri **http://localhost:3000** e clicca **"Aggiorna annunci"** in homepage per
lanciare il primo scraping, oppure usa la CLI qui sotto.

### 4. Scraping via CLI

```powershell
cd backend
python -m scraper.runner                      # tutti i portali, città di default
python -m scraper.runner --portal vistocasa   # un solo portale
python -m scraper.runner --city molfetta      # un'altra città
python -m scraper.geolocate                   # posizioni dalla via per chi non ne ha
```

### 5. Docker

```powershell
docker compose up -d --build     # oppure: make up
```

Lo stack Docker è da "produzione": immagini buildate (backend senza reload,
frontend col server standalone di Next, utente non-root), nessun mount del
codice, DB in `./data`. Legge `./.env`; le variabili `NEXT_PUBLIC_*` (inclusa
`NEXT_PUBLIC_CARTO_API_KEY`) finiscono nel bundle **al momento del build**,
quindi vanno in `./.env` e dopo averle cambiate serve
`docker compose build frontend`.

## URL & pagine

| URL | Descrizione |
|-----|-------------|
| http://localhost:3000/ | Homepage con bottone scan e data dell'ultimo aggiornamento |
| http://localhost:3000/search | Lista con ricerca full-text, filtri, sort, page-size |
| http://localhost:3000/map | Mappa + elenco con anteprima + disegno perimetro |
| http://localhost:3000/listing/{id} | Dettaglio con planimetrie e storico prezzi |
| http://localhost:3000/compare?ids=... | Confronto side-by-side fino a 3 |
| http://localhost:3000/favorites | Preferiti |
| http://localhost:3000/alerts | Ricerche salvate e novità |
| http://localhost:8001/docs | Swagger UI del backend |
| http://localhost:8001/metrics | Metriche Prometheus |

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
      [Pipeline] dedup + upsert + price-diff + rilevamento aste
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

All'avvio il backend crea `data/immo.db` e applica le migrazioni: `/search`
mostra "Nessun risultato" finché non lo popoli, col bottone **"Aggiorna
annunci"** (consigliato: il toast segue il progresso) o con la CLI.

Il primo scrape su Bari dura ~30-40 min (~7000 annunci). Immobiliare è il più
lento in fase di ricerca, casa.it in fase di dettaglio per via del rate-limit
prudente (il suo WAF banna i client aggressivi).

### La scansione one-click, passo per passo

1. Utente clicca **"Aggiorna annunci"** → `POST /api/v1/scrape/trigger`
2. Il backend lancia `python -m scraper.runner` come **processo detached** e
   ritorna `202 Accepted` immediatamente
3. Il processo crea un `job_id` e una `ScrapeRun` per ogni portale abilitato,
   tutte con lo stesso `job_id`
4. Ogni spider lavora in due fasi — **ricerca** (pagine dei risultati) e
   **dettaglio** (solo gli annunci nuovi) — e un ticker ogni 2s copia fase e
   avanzamento sulla sua riga
5. Il toast appare subito (aggiornamento ottimistico) e da lì interroga
   `GET /api/v1/scrape/status` ogni 2s
6. L'ETA usa la velocità misurata **nella fase corrente** (in ricerca copre
   solo le pagine di ricerca, e lo dice)
7. Alla fine: riepilogo "N verificati · M nuovi", esito per portale (⚠ se con
   errori, "(parziale)" se il catalogo non è stato visto tutto), chiusura
   automatica dopo 30s. Gli avvisi e-mail delle ricerche salvate partono qui.

Se il backend crasha o viene riavviato durante lo scan, il subprocess
**sopravvive**. Una run senza heartbeat da troppo tempo viene marcata
`failed` (worker morto).

### La ricerca su `/search`

- **Filtri collassabili** in sidebar. Ogni scelta aggiorna un query param via
  **nuqs**, visibile in URL; React Query rileva il cambio di chiave → refetch.
- I filtri attivi diventano **chip** sopra la lista, con X singola.
- La casella di ricerca usa **FTS5** con prefissi: le parole italiane vengono
  troncate alla radice, così singolare e plurale trovano gli stessi annunci.
- **Pubblicato**: ultimi N giorni o da una data; **Aste**: tutte / solo /
  escludi.
- **Sort**: data / prezzo / €/m² / superficie, con `NULLS LAST`.
- **Bottone "Mappa"** → `/map` preservando *tutti* i filtri.

### La mappa

- **Elenco a sinistra**, mappa a destra (su telefono: interruttore
  Mappa/Elenco). Hover su una riga → il pin si evidenzia; click su un pin →
  la riga si apre e scorre in vista.
- **Anteprima**: cliccando una riga si espande (le altre si compattano) con
  foto, dati, dotazioni e descrizione. L'altezza si adatta per mostrare tutti
  i dati senza scrollare; si ridimensiona trascinando la maniglia (o ↑/↓,
  doppio clic per tutta altezza).
- **Pan/zoom** → il bbox della viewport filtra i marker; i pin vicini si
  raggruppano in cluster (supercluster) col numero di annunci.
- **Disegna area** (matita): click per i vertici, **Invio**/"Termina" per
  chiudere (≥3 vertici), **Esc** per annullare. Il polygon va in URL come
  `polygon=lat,lng;lat,lng;...`; il backend pre-filtra sulla bounding box
  (indicizzata) e rifinisce con point-in-polygon.

### Storico e variazione prezzo

Quando lo scraper ritrova un annuncio noto con un **prezzo diverso sulla
pagina di ricerca** (tolleranza €1), aggiorna `price`, `price_previous`,
`price_changed_at` e aggiunge un punto a `listing_price_history`. Il badge
mostra il delta % (↓ verde / ↑ rosso, tooltip "Variato N giorni fa · prima
€X"); il dettaglio mostra il grafico. Portali con prezzo dalle pagine di
ricerca: Immobiliare.it, Casa.it, RE/MAX, Vistocasa, Wikicasa, Subito.

### Ricerche salvate

"Salva ricerca" memorizza i filtri correnti. `/alerts` conta per ognuna gli
annunci nuovi e i ribassi da quando l'hai vista l'ultima volta ("segna come
vista" sposta il segnalibro). Con SMTP configurato, dopo ogni scansione arriva
un'e-mail con le novità di tutte le ricerche.

### Refresh mentale del flusso

Se qualcosa non funziona, chiediti in che punto della catena sei:

- **Non vedo l'annuncio nella lista** → è nel DB? (`sqlite3 data/immo.db
  "SELECT COUNT(*) FROM listings WHERE ..."`). Se sì è un problema API/UI;
  se no è un problema scraper.
- **Il toast non appare mai** → `GET /api/v1/scrape/status` risponde? La
  scan sta scrivendo righe `scrape_runs`?
- **Una scansione è "completata con errori"** → `GET
  /api/v1/scrape/runs/{id}/errors` elenca gli errori strutturati (http,
  network, parse, blocked…).
- **Il polygon non filtra** → la stringa `polygon` in URL è ben formata
  (almeno 3 vertici)?

## API principali

La API canonica è `/api/v1` (documentata in `/docs`); `/api` resta come alias
non versionato. Se `ADMIN_TOKEN` è impostato, gli endpoint che modificano
richiedono l'header `X-Admin-Token`.

| Endpoint | Descrizione |
|----------|-------------|
| `GET /api/v1/listings` | Ricerca paginata: filtri, `q` (full-text), `polygon`, `bbox`, `sort`, `page_size` |
| `GET /api/v1/listings/map` | Marker snelli per la mappa (max 2000) |
| `GET /api/v1/listings/{id}` | Dettaglio con tutte le `sources` |
| `GET /api/v1/listings/{id}/similar` | Annunci simili |
| `GET /api/v1/listings/{id}/price-history` | Storico prezzi |
| `GET/PUT/DELETE /api/v1/favorites…` | Preferiti |
| `GET/POST/PATCH/DELETE /api/v1/alerts…` | Ricerche salvate; `POST /alerts/{id}/seen` |
| `POST /api/v1/scrape/trigger` | Lancia lo scraping come subprocess (202 immediato) |
| `GET /api/v1/scrape/status` | Avanzamento del job più recente |
| `GET /api/v1/scrape/last-update` | Ultimo aggiornamento, complessivo e per portale |
| `GET /api/v1/scrape/runs` · `/runs/{id}/errors` · `/errors` | Cronologia ed errori |
| `GET /api/v1/stats` | Contatori per portale/città, media €/m² |
| `GET /metrics` | Metriche Prometheus |
| `GET /health` | Healthcheck |

## Osservabilità

**Metriche** (`/metrics`, formato Prometheus; `METRICS_ENABLED=false` per
spegnerle se l'API è esposta):

| Metrica | Cosa misura |
|---------|-------------|
| `immo_http_request_duration_seconds{method,route,status}` | Latenza API per route (template, non path) |
| `immo_listings{portal,state}` | Annunci attivi/inattivi per portale |
| `immo_scrape_running` | Scansioni in corso |
| `immo_scrape_last_success_timestamp_seconds{portal}` | Ultima scansione riuscita — l'allarme utile è sulla sua età |
| `immo_scrape_last_duration_seconds{portal}` · `_last_status` · `_last_coverage_complete` · `_last_listings{kind}` | Esito dell'ultima scansione per portale |
| `immo_scrape_errors_total{portal,kind}` | Errori di scraping per tipo |

Le scansioni girano in un processo separato: queste cifre vengono lette dal DB
condiviso a ogni richiesta, non da contatori in memoria.

**Errori** — con `SENTRY_DSN` impostato, le eccezioni non gestite di API e
scraper (più crash degli spider ed errori della pipeline) vanno su Sentry,
etichettate `component=api|scraper`, senza dati personali.

## Architettura

```
backend/
  app/
    api/           Endpoint FastAPI (listings, favorites, alerts, scrape, stats, metrics)
    models/        SQLAlchemy: Listing, ListingSource, ListingPriceHistory,
                   ScrapeRun, ScrapeError, Favorite, SearchAlert
    schemas/       Pydantic DTOs
    services/      Business logic (filtri, FTS, dedup, avvisi, scheduler)
    observability.py  Sentry + middleware delle metriche
  alembic/         Migrazioni (applicate all'avvio)
  scraper/
    spiders/       10 spider + BaseSpider + PlaywrightSpider (idealista)
    utils/         Rate limiter, JSON-LD, RSC flight (Next.js), payload Nuxt, HTML extract
    pipeline.py    Dedup + upsert batch, price-diff, aste, disattivazione
    runner.py      Orchestratore CLI + ticker async per il progress DB
  tests/           pytest (API, parser, pipeline, migrazioni) — mai sul DB reale
frontend/
  src/app/         Pagine: home, search, map, listing/[id], compare, favorites, alerts
  src/components/
    listings/      Card, icone delle caratteristiche, badge prezzo/asta, storico
    search/        FilterFields (condivisi), sidebar, chip, salva ricerca
    map/           MapView (Leaflet + cluster), righe con anteprima, filtri
    scrape/        Toast di avanzamento (montato in RootLayout)
    ui/            Badge, Skeleton, ImageLightbox
  src/hooks/       useListings, useScrapeStatus, …
  src/lib/         api client, types, utils di formattazione
```

## Deep dive per contributori

Le scelte non-ovvie del codice, per chi ci mette mano:

### Scraping — snapshot immutabile
Il pipeline (`scraper/pipeline.py`) usa `get_known_source_ids(portal)` per
sapere quali annunci sono già in DB. Lo spider salta il detail-fetch per
questi, e il pipeline si limita a bumpare `last_seen_at`, aggiornare l'URL e
il prezzo se è cambiato. Nessun altro campo viene sovrascritto. Per forzare
un re-fetch: `DELETE FROM listings WHERE source_id = ?` e rilancia.

### Scraping — copertura e disattivazione
Una scansione è "a copertura completa" solo se ha percorso tutte le pagine di
ricerca senza crash né blocchi. Solo allora gli annunci di quel portale, **in
quelle città**, non visti da `LISTING_INACTIVE_DAYS` giorni vengono
disattivati: una scansione troncata o bloccata non "cancella" annunci che
semplicemente non ha raggiunto. Un 404/410 in dettaglio è registrato come
annuncio rimosso, non come errore.

### Scraping — circuit breaker ed errori strutturati
Dopo `SCRAPE_CIRCUIT_BREAKER_THRESHOLD` richieste fallite di fila lo spider
smette di colpire il portale per il resto della run (bloccato o giù) invece
di aggravare il ban. Ogni errore finisce in `scrape_errors` con tipo, URL e
status.

### Scraping — publication_date via CDN
Gabetti e Vistocasa non pubblicano date nell'HTML. Trucco: HEAD sulla prima
immagine → il `Last-Modified` del CDN è un buon proxy della data di
pubblicazione. Vedi `_pub_date_from_image()` in `gabetti.py` e `vistocasa.py`.

### Scraping — casa.it
Il parser legge, in ordine, `__NEXT_DATA__` (`pdp`), JSON-LD, coppie
etichetta/valore e testo; ogni gruppo di campi ha il suo estrattore in
`casa.py`. Le immagini sono su `https://images-1.casa.it/{size}/listing/{mediaid}`:
senza il segmento `/listing/` il CDN torna 400.

### Scraping — Wikicasa (Nuxt)
Le pagine portano i dati nello script `__NUXT_DATA__`, serializzato con
*devalue*: un array piatto in cui oggetti e liste contengono indici dello
stesso array. `scraper/utils/nuxt.py` lo ricostruisce; lo spider legge gli
store Pinia (`realEstateListingStoreId` per la ricerca, 25 card per pagina;
`realEstateDetailsStoreId` per il dettaglio). Le aste sono un elenco a parte
(`/asta-case/…`), percorso dopo le vendite. Il prezzo di un'asta è il prezzo
base, anche sulla card (dove `price` è l'offerta minima), altrimenti ogni
scansione segnalerebbe un falso ribasso. Con la posizione nascosta il sito
dà il centro città: in quel caso niente coordinate.

### Scraping — Subito, con prudenza
Subito è dietro DataDome, quindi lo spider non apre mai un annuncio: le
pagine di ricerca (Next.js, `__NEXT_DATA__`) contengono già tutto — testo,
foto, superficie, locali, piano, stato, classe energetica, dotazioni,
privato/agenzia. Una scansione di Bari sono ~35 richieste, una ogni 5
secondi. Subito non dà indirizzo né coordinate: un annuncio va sulla mappa
se la sua descrizione nomina la via. Gli URL di ricerca richiedono regione e provincia:
i comuni supportati sono in `_AREAS` (Bari e provincia, capoluoghi pugliesi).

### Scraping — Bakeca e TrovaCasa
**Bakeca** ripubblica annunci di agenzie e privati: la ricerca
(`{città}.bakeca.it/annunci/vendita-case/page/N/`) ha un JSON-LD per annuncio
con prezzo, comune e coordinate; il sottodominio copre la provincia, le card
degli altri comuni vengono saltate. Il dettaglio aggiunge descrizione
completa, foto, tipologia, m², classe energetica e quartiere.

**TrovaCasa** è il secondo portale del gruppo Immobiliare.it: i suoi annunci
sono in gran parte quelli di Immobiliare, che abbiamo già completi. Lo
spider quindi non apre gli annunci: le card della ricerca hanno tipo, via
nel titolo, quartiere, m², locali, prezzo, inizio della descrizione,
etichette (posto auto, ascensore, riscaldamento…) e foto — ~125 pagine per
Bari invece di ~3.000 richieste. Parte del testo del sito è UTF-8 codificato
due volte ("Ã¨" per "è"): `fix_mojibake` lo ripara.

### Mappa — posizioni approssimate
`app/services/geolocate.py`, eseguito alla fine di ogni scansione (e a mano
con `python -m scraper.geolocate`). Per ogni annuncio attivo senza
coordinate cerca una via: nell'indirizzo, nel campo zona (alcuni portali ci
mettono la via) o nel titolo/descrizione ("…San Pasquale Alta, Via
Fanelli"). La posizione viene prima dai nostri dati — la mediana degli
annunci con coordinate esatte su quella via — e altrimenti da Nominatim
(OpenStreetMap) secondo la sua policy: una richiesta al secondo, User-Agent
identificativo, ogni risposta (anche negativa) in cache in `geocode_cache`.
Un risultato a più di 25 km dal comune è una via omonima altrove e viene
scartato. `geo_precision` registra `address` (civico) o `street` (centro
della via): la mappa disegna il pin tratteggiato e lo sposta di qualche
metro in modo deterministico, così più annunci sulla stessa via non si
sovrappongono; la deduplicazione ignora queste coordinate; appena un
portale dà la posizione vera, la stima viene sostituita.

### Scraping — RE/MAX (Next.js RSC)
Il sito non ha più HTML con i dati: stanno nel "flight" React Server
Components nelle `<script>`. `scraper/utils/rsc.py` ricompone il payload e
risolve i riferimenti `$NN` ai blocchi di testo.

### Scraping — pagination ASP.NET (vistocasa)
Vistocasa è WebForms puro con `__doPostBack`: lo spider fa GET → POST con
`__EVENTTARGET` + `__VIEWSTATE` rigenerato per pagina; tre POST falliti di
fila → stop (sessione morta).

### Scraping — scritture in lotti e `BEGIN IMMEDIATE`
La pipeline salva 25 annunci per volta, con un SAVEPOINT per annuncio. Il
lotto apre la transazione con `BEGIN IMMEDIATE`: senza, il primo SAVEPOINT
apriva una transazione *differita* e, se il battito di avanzamento del
runner faceva commit tra una lettura e una scrittura, SQLite rifiutava la
scrittura ("database is locked") e il lotto andava perso.

### Backend — scrape trigger come subprocess detached
`POST /scrape/trigger` **non** usa `BackgroundTasks` (morirebbero al prossimo
reload di uvicorn): lancia `python -m scraper.runner` come processo
indipendente, che scrive sul DB condiviso; `/scrape/status` aggrega le run per
`job_id`. I riavvii del backend non interrompono lo scraping.

### Backend — ricerca full-text
`listings_fts` è un indice FTS5 *external content* sincronizzato da trigger.
Le parole cercate diventano prefissi troncati alla radice ("terrazzo" →
`terrazz*`), così singolare/plurale/femminile trovano gli stessi annunci.

### Backend — polygon filter
Pre-filtro SQL sulla bounding box (indicizzata via `lat`/`lng`), poi
ray-casting in Python. Per qualche migliaio di righe è <5ms; oltre i 100k
annunci conviene PostGIS.

### Frontend — nuqs come single source of truth
Ogni filtro vive in URL via `nuqs`: refresh conserva lo stato, URL
condivisibili, navigazione Search↔Map preserva i filtri. Esclusi di proposito
`bbox` (specifico della viewport) e `page` (torna a 1 cambiando filtro).

### Frontend — immagini
Le foto vengono dai CDN dei portali, che bloccano l'hotlinking lato server:
niente `next/image`, ma riscrittura dell'URL verso la variante della
dimensione giusta (`imageVariant`) e `referrerPolicy="no-referrer"`.

## Configurazione

Variabili principali (elenco completo in `.env.example` e
`frontend/.env.local.example`):

| Variabile | Default | Note |
|-----------|---------|------|
| `DATABASE_URL` | `data/immo.db` alla root | Lasciala non impostata in locale |
| `SCRAPE_DEFAULT_CITY` | `bari` | Città del run CLI e del bottone scan |
| `SCRAPE_SCHEDULE_ENABLED` / `SCRAPE_INTERVAL_HOURS` | `false` / `6` | Scansioni periodiche automatiche (opt-in) |
| `SCRAPE_<PORTALE>_ENABLED` | `true` | Uno per portale (immobiliare, casa, tecnocasa, remax, gabetti, vistocasa, wikicasa, subito, bakeca, trovacasa) |
| `SCRAPE_IDEALISTA_ENABLED` | `false` | DataDome blocca — servirebbe un proxy residenziale |
| `SCRAPE_RATE_LIMIT_RPM` / `SCRAPE_RATE_LIMITS` | 60 / per portale | Richieste al minuto (casa.it 30, Wikicasa 30, Bakeca 30, TrovaCasa 20, Subito 12) |
| `GEOCODER_ENABLED` | `true` | Posizioni approssimate anche via Nominatim; `false` = solo i nostri dati |
| `SCRAPE_MAX_PAGES` | 200 | Tetto di pagine di ricerca per portale |
| `SCRAPE_CONCURRENCY` | 4 | Detail fetch concorrenti per spider |
| `DEDUP_THRESHOLD` | 0.85 | Score cross-portale per considerare due annunci uguali |
| `LISTING_INACTIVE_DAYS` | 14 | Giorni senza avvistamenti prima di disattivare (solo con copertura completa) |
| `ADMIN_TOKEN` / `NEXT_PUBLIC_ADMIN_TOKEN` | vuoto | Protegge gli endpoint che modificano; i due valori devono coincidere |
| `SMTP_HOST`, `SMTP_*`, `ALERT_EMAIL_TO` | vuoto | E-mail di riepilogo delle ricerche salvate |
| `METRICS_ENABLED` | `true` | Espone `/metrics` |
| `SENTRY_DSN` / `SENTRY_ENVIRONMENT` / `SENTRY_TRACES_SAMPLE_RATE` | vuoto / `development` / `0.0` | Errori su Sentry |
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | URL del backend visto dal browser |
| `NEXT_PUBLIC_CARTO_API_KEY` | vuoto | Mappe CARTO; senza, OpenStreetMap |

## Deduplicazione — algoritmo

Score pesato in `app.services.dedup_service.find_duplicate`:

- **Indirizzo normalizzato**: 35%
- **Prezzo** (tolleranza ±10%): 20%
- **Superficie** (tolleranza ±10%): 20%
- **Geolocalizzazione** (distanza haversine): 15%
- **Numero stanze**: 10%

Soglia ≥ 0.85 per il merge. Se la posizione non è confrontabile (manca
l'indirizzo o mancano le coordinate da una delle due parti, come per Subito)
restano solo prezzo, superficie e locali: la soglia sale a 0.95, cioè
prezzo e superficie quasi identici. Un annuncio d'agenzia ripubblicato si
fonde comunque; due case diverse con misure simili no.

Il portale che viene prima in `PORTAL_PRIORITY = ["immobiliare", "casa",
"tecnocasa", "gabetti", "remax", "vistocasa", "wikicasa", "bakeca",
"trovacasa", "subito", "idealista"]` resta canonical; gli altri diventano `ListingSource`. Se arriva
un match da un portale con priorità più alta, `_promote_listing` sovrascrive i
campi canonical mantenendo stabile `listing.id`.

## Test e qualità

```powershell
cd backend
pytest -q          # ~220 test: API, parser (HTML sintetico), pipeline, migrazioni
ruff check .

cd ..\frontend
npm run lint
npm run typecheck
```

I test girano ciascuno su un DB SQLite temporaneo e non possono lanciare
processi: il DB reale `data/immo.db` non viene mai toccato. Gli hook
pre-commit (`pre-commit install`) eseguono ruff, eslint e tsc; la CI su GitHub
esegue test, lint, typecheck, build del frontend e build delle immagini Docker.

## Troubleshooting

**"Il bottone Aggiorna annunci non fa nulla"** — Controlla nei log del backend
che la POST a `/api/v1/scrape/trigger` sia arrivata (con `ADMIN_TOKEN`
impostato serve anche `NEXT_PUBLIC_ADMIN_TOKEN`). Poi verifica il subprocess:
`tasklist | findstr python`.

**"Il toast dice: nessun aggiornamento da N s"** — Lo scraper è bloccato
(spesso casa.it rate-limitato). Aspetta o termina il processo del runner: la
run verrà marcata `failed`.

**"Sulla mappa compare API KEY REQUIRED"** — Le mappe CARTO richiedono una
chiave: impostala in `NEXT_PUBLIC_CARTO_API_KEY` (in `frontend/.env.local`, o
in `.env` per Docker) e riavvia/ribuilda il frontend. Senza chiave si usa
OpenStreetMap.

**"Il backend non risponde più dopo aver salvato un file"** — Su Windows
`uvicorn --reload` a volte resta bloccato in "Shutting down": riavvialo.

**"Casa.it torna 400 sulle immagini"** — L'URL deve contenere `/listing/`.

## Note di progetto

- **Il DB `data/immo.db` non è versionato**: il primo scraping è necessario
  per popolarlo. I backup pre-migrazione sono in `data/backups/`.
- **Backend sulla porta 8001 in sviluppo** (la 8000 è spesso occupata): il
  frontend la trova tramite `NEXT_PUBLIC_API_URL` in `frontend/.env.local`.
  Docker usa la 8000.
