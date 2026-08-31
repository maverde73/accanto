# 01 — Architettura

## Vista d'insieme

```
┌──────────────┐
│ Redmi Watch 6│  Xiaomi Vela (RTOS). Non programmabile. Solo sorgente dati.
│   M2523W1    │  Sensori: HR, passi, sonno, SpO2, GPS (solo tracce allenamento).
└──────┬───────┘
       │ BLE proprietario cifrato (gestito da Mi Fitness, non da noi)
       ▼
┌─────────────────────────────────────────────────────────────┐
│ Samsung Galaxy S24 (Android)                                 │
│                                                              │
│  ┌────────────┐   Health Connect    ┌──────────────────────┐ │
│  │ Mi Fitness │ ──────────────────▶ │  Collector "Accanto" │ │
│  └────────────┘  (HR, passi, sonno) │  (app nativa Kotlin) │ │
│                                     │                      │ │
│  Sensori telefono ─────────────────▶│  - Foreground service│ │
│  (GPS, accel, activity,             │  - Coda locale (Room)│ │
│   unlock, screen, batteria)         │  - Uploader batch    │ │
│                                     │  - Command executor  │ │
│                                     └──────────┬───────────┘ │
└────────────────────────────────────────────────┼────────────┘
        ▲ comandi (FCM downstream)                │ HTTPS (ingest + ack)
        │                                         ▼
┌───────┴─────────────────────────────────────────────────────┐
│ Backend (FastAPI + PostgreSQL)                               │
│  - Ingest idempotente          - Liveness engine             │
│  - Autorizzazioni / grant      - Command dispatcher (→ FCM)  │
│  - Alert engine                - Realtime hub (WS/SSE)       │
│  - Audit log                                                 │
└───────┬─────────────────────────────────────────────────────┘
        │ HTTPS (REST) + WebSocket/SSE (push)
        ▼
┌─────────────────────────────────────────────────────────────┐
│ Viewer (Next.js web app) — usato dai caregiver               │
│  - Dashboard presenza   - Mappa live (MapLibre + OSM)        │
│  - Check-in / escalation - Storico e trend                   │
└─────────────────────────────────────────────────────────────┘
```

## I tre componenti

### 1. Collector (Android nativo)

**Responsabilità:** essere gli occhi e le mani del sistema sul telefono del
subject.

- Lettura **Health Connect** (battito, passi, sonno) con changes-token polling.
- Lettura **sensori del telefono**: GPS (FusedLocationProvider), Activity
  Recognition, step counter, eventi di sblocco/schermo, batteria.
- **Foreground service** persistente: è il cuore che tiene vivo tutto.
- **Coda locale** (Room) con upload batch **resiliente all'offline** e
  ritrasmissione idempotente.
- **Command executor**: riceve comandi via FCM (sync forzato, vibrazione,
  suoneria, richiesta di conferma, canale audio) e li esegue.

**Perché nativo e non Flutter:** il punto fragile del progetto è esattamente il
lavoro in background, i permessi speciali e l'interazione con Health Connect —
proprio l'area dove il layer nativo Android soffre meno e i wrapper cross-platform
soffrono di più. Lo stack Flutter del team resta valido altrove, non qui.
Motivazione estesa in [`08-collector-android.md`](08-collector-android.md).

### 2. Backend (FastAPI + PostgreSQL)

**Responsabilità:** verità unica del sistema, autorizzazione, orchestrazione.

- **Ingest idempotente** degli eventi (dedup su chiave deterministica).
- **Liveness engine**: ricalcola lo `liveness_snapshot` a ogni ingest.
- **Grant / autorizzazioni**: chi può vedere cosa, con quale granularità e fino a
  quando.
- **Command dispatcher**: traduce le azioni del caregiver in push FCM verso il
  collector, e traccia stato/ack.
- **Alert engine**: regole lato server (soglie, assenza dati, geofence).
- **Realtime hub**: WebSocket/SSE verso i viewer.
- **Audit log**: ogni lettura sensibile e ogni azione di escalation.

**Perché FastAPI + Postgres:** stack noto al team, type hints, ottimo supporto
async per il realtime. Postgres copre tutto in fase 1; **TimescaleDB** è
un'estensione opzionale (drop-in) se e quando il volume dei campioni lo richiede —
la scelta non è bloccante e non cambia lo schema.

### 3. Viewer (Next.js web app)

**Responsabilità:** interfaccia del caregiver.

- **Web, non app installabile.** Per lo scopo "chiunque io autorizzi", un link è
  più semplice da distribuire *e da revocare* di un APK. Nessuno store, nessun
  aggiornamento forzato.
- Dashboard presenza, mappa live con geofence, pannello check-in/escalation,
  storico e trend.
- Notifiche push al caregiver via Web Push (per gli alert generati dal backend).

## Flussi principali

### A. Flusso passivo (steady state)

```
Sensori telefono / Health Connect
   → Collector accoda evento (occurred_at = ora del device)
   → upload batch (anche in ritardo, idempotente)
   → Backend ingest → aggiorna liveness_snapshot
   → Realtime hub → Viewer aggiorna lo stato
```

Event-driven, non a polling: sblocchi e schermo sono broadcast gratuiti, activity
recognition e step counter sono in hardware, il GPS in idle usa spostamento
significativo. Consumo batteria minimo.

### B. Check-in on-demand

```
Caregiver preme "Come sta?"
   → Backend crea checkin_request (status=pending) → push FCM high-priority
   → Collector si sveglia (esente Doze), raccoglie segnali telefono ISTANTANEI,
     lancia Mi Fitness in foreground per forzare il sync del battito
   → upload → Backend aggiorna checkin_request (status=answered) + snapshot
   → Realtime → Viewer mostra risposta PROGRESSIVA:
       prima i segnali telefono (secondi), poi il battito (decine di secondi)
```

Dettaglio in [`04-escalation-ladder.md`](04-escalation-ladder.md).

### C. Escalation attiva

```
Caregiver sceglie un gradino (vibra / conferma / audio)
   → Backend crea escalation_action → push FCM
   → Collector esegue (notifica → watch vibra, allarme full-screen, audio…)
   → eventuale risposta del subject ("sto bene") → evento Tier A fortissimo
   → tutto registrato in audit_log
```

### D. Mappa live

```
Caregiver apre la mappa
   → Backend segnala al collector: passa a location "live mode" (alta precisione, ~5s)
   → Collector invia location_fix frequenti
   → Realtime → pallino si muove sulla mappa
   → Caregiver chiude → collector torna in idle mode (batteria)
```

## Principi trasversali

1. **`occurred_at` ≠ `received_at`.** Ogni dato porta due tempi: quando è successo
   (orologio del device) e quando è arrivato (server). La UI usa **sempre** il
   primo. Confonderli è l'errore più insidioso dell'intera architettura: un batch
   di dati vecchi che arriva ora **non** è attività attuale.
2. **Idempotenza ovunque.** Il collector ritrasmette dopo ogni disconnessione;
   ogni evento ha una `dedup_key` deterministica; il backend fa upsert.
3. **Assenza di dati ≠ allarme.** Grigio = "non so". Ambra = "so, ed è quieto".
   Rosso = **solo** evidenza positiva di un problema.
4. **Autorizzazione per-metrica e per-scadenza.** Non "accesso sì/no", ma "questo
   caregiver, queste metriche, questa granularità, fino a questa data".
5. **Trasparenza come feature.** Escalation e audio sono visibili e registrati;
   niente comportamenti occulti.

## Scelte tecnologiche (riassunto)

| Layer | Scelta | Alternative valutate | Perché |
|-------|--------|----------------------|--------|
| Collector | Kotlin nativo | Flutter | Background service + Health Connect + permessi speciali |
| Dati dal watch | Health Connect | BLE reverse-engineered | Legittimo, stabile, non ruba la connessione a Mi Fitness |
| Posizione | GPS telefono | GPS watch | Il watch non espone GPS live; il telefono è con la persona |
| Backend | FastAPI + Postgres | Node/Express | Stack del team, async, type hints |
| Serie temporali | Postgres (+ Timescale opz.) | InfluxDB | Un solo datastore in fase 1 |
| Realtime | WebSocket/SSE | polling | Push a bassa latenza ai viewer |
| Viewer | Next.js web | app nativa/Flutter | Link autorizzabile/revocabile, zero install |
| Mappa | MapLibre GL + tile OSM | Google Maps | No API key, no costi, self-hostabile |
| Push al collector | FCM | — | Wake da Doze con priorità alta |
