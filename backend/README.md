# Accanto — backend

FastAPI + PostgreSQL. Verità unica del sistema: ingest, calcolo della presenza,
autorizzazioni, canale comandi, realtime.

Progetto complessivo: [`../README.md`](../README.md) ·
design: [`../docs/09-backend.md`](../docs/09-backend.md).

## Avvio rapido

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
cp .env.example .env
docker run -d --name accanto-pg -e POSTGRES_USER=accanto -e POSTGRES_PASSWORD=accanto -e POSTGRES_DB=accanto -p 5432:5432 postgres:16-alpine
.venv/bin/alembic upgrade head
.venv/bin/uvicorn app.main:app --reload
```

API su `http://localhost:8000`, documentazione interattiva su `/docs`.

## Test

```bash
.venv/bin/python -m pytest -q
```

I test del dominio **non richiedono un database**: `app/domain/` è stdlib puro,
senza I/O. È deliberato — la logica che decide cosa vede un caregiver dev'essere
verificabile in millisecondi.

I test di integrazione girano solo se punti a un PostgreSQL vero:

```bash
ACCANTO_TEST_DATABASE_URL=postgresql+asyncpg://accanto:accanto@localhost:5432/accanto \
  .venv/bin/python -m pytest -q
```

Senza quella variabile si saltano automaticamente. Sono su Postgres reale e non
su SQLite perché ciò che va verificato — `ON CONFLICT DO NOTHING`, `DISTINCT ON`,
JSONB, colonne array — su SQLite non esiste: simularlo vorrebbe dire testare il
simulatore.

## Struttura

```
app/
  domain/        logica pura: tier, presenza, scope, geo, alert, comandi (no I/O)
  models/        17 tabelle SQLAlchemy
  schemas/       contratti Pydantic
  repositories/  accesso dati
  services/      orchestrazione (liveness, ingest, commands, alerts, grants)
  realtime/      hub WebSocket con filtro per scope
  adapters/      push FCM (con sender di sviluppo che logga)
  api/           router e dipendenze
  core/          config, DB, auth, sicurezza
alembic/         migrazioni
```

La dipendenza va **sempre** verso l'interno: `api → services → repositories →
models`, e `domain` non dipende da nulla.

## Invarianti protette da test di regressione

Non sono dettagli: sono ciò che decide se il prodotto è affidabile.

1. **La fusione non produce mai il rosso.** Verificato su tutte le combinazioni
   di freschezza dei quattro orologi.
2. **Il silenzio totale è grigio**, mai ambra o verde.
3. **`no_data` non può essere configurato rosso**, e l'API restituisce la
   `effective_severity` così l'owner vede il cap invece di crederlo attivo.
4. **La headline porta l'ora dell'evento**, non quella del sync.
5. **Il tier è derivato dal server**, mai dal payload del client.
6. **Un caregiver `location:coarse` non riceve mai le coordinate esatte** — né
   via REST né via WebSocket. La riduzione avviene sul server.
7. **La revoca di un grant taglia l'accesso subito**, con la stessa sessione.
8. **La scadenza di un grant è verificata alla lettura**, non da un cron.

## Scelte di implementazione da conoscere

- **`access_grant`, non `grant`**: `GRANT` è parola riservata SQL.
- **404 invece di 403** per un subject non autorizzato: confermare che una
  persona esiste è già una divulgazione.
- **Token device**: SHA-256 (stringhe casuali ad alta entropia). Argon2 resta
  per le password utente.
- **Comandi firmati in HMAC**: i gradini 4-5 non si eseguono mai sul solo
  payload della push. Il collector rivalida con `GET /v1/commands/{id}`.
- **Le push sono best-effort**: `GET /v1/commands/pending/list` permette al
  collector di recuperare ciò che ha perso.
- **`NoDecode` su `cors_origins`**: senza, pydantic-settings tenta di decodificare
  come JSON il valore d'ambiente prima dei validator, e la forma documentata
  separata da virgole farebbe crashare l'avvio.
- **Bucketing dedup a finestre fisse**: la chiave dev'essere calcolabile da un
  evento isolato. Il debounce vero è del collector.

## Limiti noti

- **Il realtime hub è in-process.** Con più worker serve un broker condiviso
  (Redis pub/sub) dietro la stessa interfaccia; la superficie
  publish/subscribe è volutamente stretta per rendere lo scambio locale.
- **Nessun rate limiting** ancora (previsto su ingest ed escalation).
- **Web Push ai caregiver** non implementato: `push_token` esiste, il mittente no.
- **`activity_baseline`** è solo schema; il calcolo arriva in fase 3.

## Stato

Fasi 1 e 2 del backend complete: dominio, 17 tabelle con migrazioni, ingest
idempotente, autorizzazione per scope, check-in on-demand, scala di escalation,
canale comandi firmato, realtime con filtro scope, alert engine, audit.

**139 test passano** (dominio + integrazione su PostgreSQL reale).
