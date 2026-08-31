# 09 — Backend

FastAPI + PostgreSQL. Verità unica del sistema, autorizzazione, orchestrazione.

## Stack

| Ambito | Scelta |
|--------|--------|
| Linguaggio | Python 3.12+, type hints ovunque |
| Framework | FastAPI (async) |
| DB | PostgreSQL 16 (+ TimescaleDB opzionale) |
| ORM / query | SQLAlchemy 2.x (async) + Alembic (migrazioni) |
| Validazione | Pydantic v2 |
| Realtime | WebSocket nativo FastAPI (+ SSE fallback) |
| Push al collector | FCM (Firebase Admin SDK) |
| Push ai caregiver | Web Push (VAPID) |
| Auth | OAuth2 password flow + JWT (o provider esterno), token per-device |
| Task/schedule | APScheduler o worker separato (alert engine, retention) |

## Architettura a layer

Coerente con le convenzioni globali (route → service → repository, DI,
config esternalizzata):

```
api/            ← router FastAPI, dipendenze di auth/scope, schemi Pydantic
  ingest.py     ← POST /ingest/*
  commands.py   ← command channel
  subjects.py   ← snapshot, timeline, checkin, escalate
  location.py   ← latest, track, live
  grants.py     ← autorizzazioni
  alerts.py, geofences.py, audit.py, auth.py
services/       ← logica di dominio (NO SQL diretto, NO dettagli HTTP)
  liveness.py   ← LivenessEngine: calcola liveness_snapshot
  ingest.py     ← idempotenza, dedup, fan-out realtime
  command.py    ← CommandDispatcher (→ FCM), firma, ack
  escalation.py ← orchestrazione gradini
  alerts.py     ← AlertEngine (regole, anti-falso-allarme)
  grants.py     ← verifica scope + scadenza
repositories/   ← accesso dati (SQLAlchemy), un repo per aggregato
realtime/       ← hub connessioni, fan-out per subject, filtro scope
core/           ← config, sicurezza, dipendenze, errori
```

## LivenessEngine (componente centrale)

Ricalcola lo `liveness_snapshot` **a ogni ingest** rilevante:

```python
def recompute(subject_id) -> LivenessSnapshot:
    cfg   = load_subject_config(subject_id)          # FRESH_*, NIGHT_*, override
    now   = utcnow()
    clocks = latest_occurred_at_per_tier(subject_id) # A/B/C/D via indice
    night = is_night(now, cfg)
    fresh = widen_windows(cfg, night)                # di notte finestre più larghe
    headline = choose_headline(clocks, fresh, now)   # regola di fusione (doc 03)
    charging = infer_watch_charging(subject_id, cfg) # gap HR + passi fermi
    lag   = pipeline_lag_p90(subject_id)             # received_at - occurred_at
    snap  = build_snapshot(clocks, headline, charging, lag, ...)
    upsert(snap); publish_realtime(subject_id, snap) # fan-out ai viewer
    return snap
```

Regole invarianti (da [`03`](03-liveness-model.md)), applicate **in codice**:

- l'assenza di dati produce **grigio**, mai rosso;
- una regola `no_data` non può superare severità **ambra**;
- la UI riceve `occurred_at`, mai `received_at`.

## Ingest idempotente

```python
def ingest_events(device, events):
    validate(events)                      # Pydantic: range, timestamp non futuri
    rows = [to_row(device.subject_id, e) for e in events]
    accepted, dups = upsert_on_conflict(rows, key="(subject_id, dedup_key)")
    touch_device_last_seen(device)
    if accepted:
        liveness.recompute(device.subject_id)
    return accepted, dups
```

L'upsert `ON CONFLICT DO NOTHING` sulla `unique(subject_id, dedup_key)` è ciò che
rende sicura la ritrasmissione del collector.

## CommandDispatcher ed escalation

- Traduce una richiesta del viewer in un record (`checkin_request` /
  `escalation_action`) + push FCM con solo `command_id`.
- **Firma** il comando; il collector rivalida via `GET /commands/{id}` prima di
  azioni sensibili (rung 4–5).
- Riceve `ack` e `response`, aggiorna stato, genera eventi/alert, fa fan-out
  realtime.
- Ogni comando scrive in `audit_log`.

## AlertEngine

Valutato su ingest e su schedule:

| Regola | Severità max | Nota |
|--------|--------------|------|
| `no_data` | **ambra** | mai rossa (invariante) |
| `quiet_too_long` | ambra | sensibile all'ora / baseline |
| `geofence_exit` | ambra/rossa | secondo `kind` della zona |
| `battery_low` | ambra | telefono/watch |
| `hr_range` (a persona attiva) | ambra/rossa | solo se il dato è recente e attendibile |
| conferma `need_help` | **rossa** | fonte legittima di rosso |

## Sicurezza (operativa)

- **Secret solo in env** (mai nel codice): DB URL, chiavi FCM/VAPID, JWT secret.
- **CORS**: origini esplicite in produzione (dominio del viewer), mai wildcard.
- **Validazione input** su ogni endpoint (Pydantic), coordinate in range, timestamp
  con tolleranza.
- **Rate limiting**: ingest per-device, escalation per-utente.
- **Token per-device revocabili**; JWT short-lived + refresh; revoca grant
  invalida sessioni/realtime del grantee.
- **Cifratura**: HTTPS ovunque; a riposo disco cifrato; opzionale cifratura a
  livello colonna per i vitali.
- **Niente PII/vitali/posizione in query string** né nei log applicativi.
- **Audit** di ogni lettura sensibile e azione.

## Deployment (indicativo)

- Container (Docker); backend stateless dietro reverse proxy TLS.
- Postgres gestito o container con volume cifrato e backup.
- Worker separato per alert engine + retention job.
- Env di staging e prod distinti; migrazioni via Alembic in CI.
- Osservabilità: log strutturati, metriche su lag di ingest, health endpoint.

## Testing

Per ogni feature nuova (convenzione globale):

- **unit** su LivenessEngine (tabelle di casi: combinazioni di clock/notte/ricarica
  → headline attesa) e su idempotenza ingest;
- **integration** su endpoint con DB di test (fixture per grant/scopes);
- **contract** sull'API di ingest e sul command channel (il collector dipende da
  questi contratti);
- casi di regressione per le **invarianti anti-falso-allarme** (assenza dati →
  grigio; `no_data` → mai rosso).
