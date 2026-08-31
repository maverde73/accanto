# 06 — API

Contratto tra i tre componenti. Tre superfici distinte:

1. **Ingest API** — collector → backend (upload dati).
2. **Command channel** — backend → collector (via FCM) + ack.
3. **Viewer API** — web app ↔ backend (REST + realtime).

Base URL: `https://api.accanto.example/v1`. Tutto HTTPS, tutto JSON.
Errori: problema in stile RFC 9457 (`application/problem+json`).

## Autenticazione

| Chiamante | Meccanismo |
|-----------|------------|
| Collector (device) | Bearer token opaco per-device (`device.auth_token_hash`), emesso al pairing |
| Caregiver / owner | JWT di sessione (OAuth2 password o provider esterno), short-lived + refresh |
| FCM → collector | payload firmato lato backend; il collector valida il `command_id` contro il backend prima di eseguire azioni sensibili |

Ogni richiesta del viewer è filtrata dai **grant**: il backend verifica scope +
scadenza + stato su ogni risorsa `subject`. Vedi [`07`](07-authorization-privacy.md).

---

## 1. Ingest API (collector → backend)

### `POST /ingest/events` — batch di eventi di attività

Idempotente per `dedup_key`. Il collector accumula offline e ritrasmette.

```jsonc
// request
{
  "device_id": "…",
  "events": [
    {
      "occurred_at": "2026-08-31T12:41:03+02:00",
      "source": "phone",
      "kind": "unlock",
      "tier": "A",
      "confidence": 1.0,
      "payload": { "count": 1 },
      "dedup_key": "a1b2c3…"
    },
    {
      "occurred_at": "2026-08-31T12:40:00+02:00",
      "source": "watch",
      "kind": "hr",
      "tier": "C",
      "payload": { "bpm": 72 },
      "dedup_key": "d4e5f6…"
    }
  ]
}
```

```jsonc
// response 200
{ "accepted": 2, "duplicates": 0, "snapshot_updated": true }
```

Nota: duplicati → `200`, non errore (ritrasmissione è normale).

### `POST /ingest/locations` — batch di fix di posizione

```jsonc
{
  "device_id": "…",
  "fixes": [
    { "occurred_at": "2026-08-31T12:41:00+02:00", "lat": 45.07, "lon": 7.68,
      "accuracy_m": 12.0, "speed_mps": 1.3, "battery_pct": 88, "dedup_key": "…" }
  ]
}
```

### `POST /ingest/heartbeat` — segno di vita + stato device

Anche a mani vuote: alimenta il Tier D e la salute pipeline.

```jsonc
{ "device_id": "…", "app_version": "1.4.0", "phone_battery_pct": 88,
  "watch_bt_connected": true, "permissions_ok": true, "occurred_at": "…" }
```

---

## 2. Command channel (backend → collector)

I comandi viaggiano come **push FCM high-priority**. Il payload contiene solo un
`command_id` e il tipo; il collector fa poi `GET /commands/{id}` per ottenere i
dettagli firmati (evita comandi contraffatti nel payload push).

### Tipi di comando

| `type` | Gradino | Azione sul collector |
|--------|---------|----------------------|
| `force_sync` | 2 | raccogli segnali telefono + lancia Mi Fitness per HR fresco |
| `location_live_on` / `off` | — | passa GPS a alta/bassa frequenza |
| `vibrate` | 3 | notifica → watch vibra |
| `ring` | 4 | audio su stream ALARM |
| `confirm_prompt` | 4 | full-screen "Stai bene?" con pulsanti |
| `audio_out` | 5 | riproduci messaggio/TTS |
| `audio_channel` | 5 | apri canale (annuncio + WebRTC) |

### `GET /commands/{command_id}` (collector)

```jsonc
// response
{
  "command_id": "…", "type": "confirm_prompt", "rung": 4,
  "params": { "message": "Tutto bene?", "buttons": ["im_ok","need_help"],
              "use_alarm_stream": true },
  "issued_by": "Marco", "issued_at": "…", "expires_at": "…", "signature": "…"
}
```

### `POST /commands/{command_id}/ack` (collector)

```jsonc
{ "status": "executed", "executed_at": "…", "detail": { "shown": true } }
```

Aggiorna `escalation_action.status`. Se il subject risponde:

### `POST /commands/{command_id}/response` (collector)

```jsonc
{ "response": "im_ok", "responded_at": "…", "source": "watch" }
```

→ crea `confirmation_response` + evento Tier A (o alert rosso se `need_help`).

---

## 3. Viewer API (caregiver ↔ backend)

### Presenza

| Metodo | Endpoint | Scope | Descrizione |
|--------|----------|-------|-------------|
| `GET` | `/subjects` | — | subject a cui l'utente ha un grant attivo |
| `GET` | `/subjects/{id}/snapshot` | `liveness` | headline + 4 orologi + batterie |
| `GET` | `/subjects/{id}/timeline` | `history` | eventi in un intervallo (usa `occurred_at`) |

```jsonc
// GET /subjects/{id}/snapshot
{
  "subject_id": "…",
  "computed_at": "2026-08-31T12:41:10+02:00",
  "headline": { "state": "active", "at": "2026-08-31T12:41:03+02:00",
                "evidence": "ha sbloccato il telefono", "color": "green" },
  "clocks": {
    "interaction": "2026-08-31T12:41:03+02:00",
    "movement":    "2026-08-31T12:38:00+02:00",
    "vital":       "2026-08-31T12:40:00+02:00",
    "contact":     "2026-08-31T12:41:05+02:00"
  },
  "vitals": { "bpm": 72, "bpm_at": "2026-08-31T12:40:00+02:00" },
  "batteries": { "phone_pct": 88, "watch_likely_charging": false },
  "pipeline": { "lag_seconds_p90": 34, "healthy": true }
}
```

> La UI usa **sempre** i timestamp `occurred_at` presenti qui, mai il momento
> della risposta HTTP.

### Check-in ed escalation

| Metodo | Endpoint | Scope | Descrizione |
|--------|----------|-------|-------------|
| `POST` | `/subjects/{id}/checkin` | `liveness` | avvia check-in on-demand (gradino 2) |
| `GET` | `/checkins/{id}` | `liveness` | stato/risultato (o via realtime) |
| `POST` | `/subjects/{id}/escalate` | `escalation:*` | invoca un gradino 3–5 |
| `GET` | `/subjects/{id}/escalations` | `escalation:*` | storico azioni |

```jsonc
// POST /subjects/{id}/escalate
{ "rung": 4, "action_type": "confirm_prompt",
  "params": { "message": "Tutto bene? Rispondi quando puoi." } }
// response 202
{ "escalation_id": "…", "status": "sent" }
```

Il backend verifica lo scope corrispondente (`escalation:alarm` per rung 4) prima
di accettare. Ogni chiamata scrive in `audit_log`.

### Mappa

| Metodo | Endpoint | Scope | Descrizione |
|--------|----------|-------|-------------|
| `GET` | `/subjects/{id}/location/latest` | `location:*` | ultimo fix (risoluzione secondo lo scope) |
| `GET` | `/subjects/{id}/location/track` | `location:precise`,`history` | traccia in un intervallo |
| `POST` | `/subjects/{id}/location/live` | `location:precise` | attiva/disattiva live mode |

> **Risoluzione secondo lo scope:** con `location:coarse` il backend restituisce
> coordinate arrotondate (es. a ~1 km) o solo il nome della geofence. Il filtro è
> lato server: il dato preciso non lascia mai il backend per un caregiver coarse.

### Geofence e alert

| Metodo | Endpoint | Scope | |
|--------|----------|-------|--|
| `GET/POST/DELETE` | `/subjects/{id}/geofences` | owner | gestione zone |
| `GET/POST` | `/subjects/{id}/alert-rules` | owner | regole |
| `GET` | `/subjects/{id}/alerts` | `liveness` | alert scattati |
| `POST` | `/alerts/{id}/ack` | `liveness` | presa in carico |

### Grant e audit (owner)

| Metodo | Endpoint | Descrizione |
|--------|----------|-------------|
| `GET` | `/subjects/{id}/grants` | elenco autorizzazioni |
| `POST` | `/subjects/{id}/grants` | crea (scopes, expires_at) |
| `PATCH` | `/grants/{id}` | modifica scopes/scadenza |
| `DELETE` | `/grants/{id}` | **revoca immediata** |
| `GET` | `/subjects/{id}/audit` | log accessi/azioni (anche per il subject) |

---

## 4. Realtime (backend → viewer)

Un canale per subject, autorizzato dal grant. WebSocket preferito, SSE come
fallback.

```
WS  /realtime?subject_id={id}&token={jwt}
```

Messaggi (server → client):

```jsonc
{ "type": "snapshot",  "data": { /* come GET /snapshot */ } }
{ "type": "location",  "data": { "lat": …, "lon": …, "accuracy_m": …, "at": "…" } }
{ "type": "checkin",   "data": { "id": "…", "status": "partial|answered", "result": {…} } }
{ "type": "escalation","data": { "id": "…", "status": "executed" } }
{ "type": "alert",     "data": { "id": "…", "severity": "amber|red", "title": "…" } }
```

Il canale rispetta gli scope: un caregiver senza `location:*` non riceve messaggi
`location`; con `location:coarse` li riceve arrotondati.

## Note di sicurezza

- **Rate limiting** su ingest (per device) ed escalation (per utente).
- **Firma dei comandi**: il collector non esegue azioni sensibili (rung 4–5) su
  solo payload FCM; rivalida contro `GET /commands/{id}`.
- **Validazione input** su ogni endpoint (Pydantic), coordinate in range, timestamp
  non nel futuro oltre una tolleranza.
- **Nessun dato sensibile in query string** (né posizione né vitali): sempre nel
  body o path con id opachi.
