# 05 — Modello dati

Schema PostgreSQL. Le scelte chiave (idempotenza, `occurred_at`/`received_at`,
snapshot derivato) derivano da [`01`](01-architecture.md) e [`03`](03-liveness-model.md).

Convenzioni: `snake_case`, chiavi `uuid` per le entità di dominio, `bigserial` per
gli stream ad alto volume, `timestamptz` sempre (mai `timestamp` naive).

## Diagramma delle entità

```
app_user ──< grant >── subject ──1:1── liveness_snapshot
   │                      │
   │                      ├──< device (collector)
   │                      ├──< activity_event      (stream, Tier A/B/C/D)
   │                      ├──< location_fix         (stream)
   │                      ├──< geofence
   │                      ├──< alert_rule ──< alert_event
   │                      ├──< activity_baseline    (derivato, futuro)
   │                      └──< checkin_request ──< escalation_action ──< confirmation_response
   │
   └──< push_token
audit_log  (trasversale: chi ha visto/fatto cosa)
```

## Entità di dominio

### `app_user` — account che fanno login (caregiver, owner)

```sql
create table app_user (
  id            uuid        primary key default gen_random_uuid(),
  email         text        not null unique,
  display_name  text        not null,
  password_hash text,                       -- null se solo OAuth
  created_at    timestamptz not null default now(),
  disabled_at   timestamptz
);
```

### `subject` — la persona monitorata

```sql
create table subject (
  id            uuid        primary key default gen_random_uuid(),
  display_name  text        not null,
  -- l'app_user che "possiede" il subject (spesso il subject stesso, o un tutore):
  owner_user_id uuid        references app_user(id),
  timezone      text        not null default 'Europe/Rome',
  config        jsonb       not null default '{}',  -- override FRESH_*, NIGHT_*, ecc.
  created_at    timestamptz not null default now()
);
```

`config` contiene gli override dei parametri di [`03`](03-liveness-model.md)
(`FRESH_A`, `CHARGE_GAP`, `NIGHT_START`…). Assenti → default di sistema.

### `device` — il telefono collector (e logicamente il watch)

```sql
create table device (
  id             uuid        primary key default gen_random_uuid(),
  subject_id     uuid        not null references subject(id) on delete cascade,
  kind           text        not null,      -- 'phone_collector' | 'watch'
  label          text,                      -- 'Galaxy S24 di Anna'
  -- credenziale del device per l'ingest (hash di un token opaco):
  auth_token_hash text       not null,
  fcm_token       text,                      -- per i comandi downstream
  app_version     text,
  last_seen_at   timestamptz,
  created_at     timestamptz not null default now()
);
create index on device (subject_id);
```

## Autorizzazioni

### `grant` — chi può vedere cosa, con quale granularità, fino a quando

```sql
create table grant (
  id            uuid        primary key default gen_random_uuid(),
  subject_id    uuid        not null references subject(id) on delete cascade,
  grantee_user_id uuid      not null references app_user(id) on delete cascade,
  granted_by_user_id uuid   not null references app_user(id),
  -- ambito: quali metriche e con quale dettaglio
  scopes        text[]      not null,   -- es. {'liveness','vitals','location:coarse','escalation'}
  -- ciclo di vita
  status        text        not null default 'active',  -- active|revoked|expired
  expires_at    timestamptz,            -- null = senza scadenza
  revoked_at    timestamptz,
  created_at    timestamptz not null default now(),
  unique (subject_id, grantee_user_id)
);
create index on grant (grantee_user_id) where status = 'active';
```

**Scopes previsti** (estendibile):

| Scope | Concede |
|-------|---------|
| `liveness` | stato di presenza (headline + orologi) |
| `vitals` | valori di battito, sonno |
| `location:coarse` | posizione a bassa risoluzione (città/zona) |
| `location:precise` | posizione esatta sulla mappa |
| `escalation:notify` | gradini 3 (notifica/vibrazione) |
| `escalation:alarm` | gradino 4 (allarme + conferma) |
| `escalation:audio` | gradino 5 (canale audio) |
| `history` | accesso allo storico oltre il tempo reale |

La separazione `location:coarse` vs `precise` e la scomposizione dell'escalation
sono ciò che permette grant come *"può vedere se sta bene ma non dove si trova"*.

## Stream ad alto volume

### `activity_event` — eventi grezzi, append-only

```sql
create table activity_event (
  id            bigserial   primary key,
  subject_id    uuid        not null references subject(id) on delete cascade,
  occurred_at   timestamptz not null,     -- quando è successo (orologio device)
  received_at   timestamptz not null default now(),
  source        text        not null,     -- 'phone' | 'watch'
  kind          text        not null,     -- 'unlock'|'app_usage'|'steps'|'activity'|'hr'|'bt_contact'|...
  tier          char(1)     not null,     -- 'A' | 'B' | 'C' | 'D'
  confidence    real        not null default 1.0,
  payload       jsonb       not null default '{}',  -- es. {"bpm":72} o {"activity":"WALKING"}
  dedup_key     text        not null,
  unique (subject_id, dedup_key)
);
create index on activity_event (subject_id, tier, occurred_at desc);
create index on activity_event (subject_id, kind, occurred_at desc);
```

- **`dedup_key`** deterministica (es. `sha1(subject|kind|occurred_at_troncato)`):
  il collector ritrasmette dopo ogni disconnessione, l'`unique` rende l'ingest
  idempotente. Fondamentale per i passi, che altrimenti si sommano.
- Mai `UPDATE`: è un log. Le correzioni sono nuovi eventi.

### `location_fix` — stream posizione, separato dagli eventi

```sql
create table location_fix (
  id           bigserial   primary key,
  subject_id   uuid        not null references subject(id) on delete cascade,
  occurred_at  timestamptz not null,
  received_at  timestamptz not null default now(),
  lat          double precision not null,
  lon          double precision not null,
  accuracy_m   real,               -- raggio di incertezza → cerchio sulla mappa
  speed_mps    real,
  battery_pct  smallint,           -- batteria telefono, "gratis" a ogni fix
  source       text        not null default 'phone',
  dedup_key    text        not null,
  unique (subject_id, dedup_key)
);
create index on location_fix (subject_id, occurred_at desc);
```

Separato da `activity_event` per cardinalità e pattern di query diversi.
`battery_pct` viaggia con ogni fix (costo zero) e alimenta l'inferenza "watch in
carica" e l'alert "telefono quasi scarico" senza pipeline dedicate.

> **Timescale (opzionale):** `activity_event` e `location_fix` sono i candidati
> naturali a diventare hypertable se il volume cresce. Nessuna modifica di schema
> richiesta.

## Stato derivato

### `liveness_snapshot` — una riga per subject, riscritta a ogni ingest

```sql
create table liveness_snapshot (
  subject_id            uuid primary key references subject(id) on delete cascade,
  computed_at           timestamptz not null,
  last_interaction_at   timestamptz,          -- Tier A
  last_movement_at      timestamptz,          -- Tier B
  last_vital_at         timestamptz,          -- Tier C
  last_contact_at       timestamptz,          -- Tier D
  headline_state        text not null,        -- active|moving|vitals_only|quiet|no_data
  headline_at           timestamptz,
  headline_evidence     text,                 -- 'ha sbloccato il telefono'
  latest_bpm            smallint,
  latest_bpm_at         timestamptz,
  latest_location_id    bigint references location_fix(id),
  phone_battery_pct     smallint,
  watch_likely_charging boolean not null default false,
  pipeline_lag_seconds  integer,              -- salute pipeline (P90 24h)
  updated_at            timestamptz not null default now()
);
```

Ricalcolato a ogni ingest → la query del viewer è una singola lettura per PK,
istantanea anche con milioni di eventi.

### `activity_baseline` — baseline per fascia oraria (futuro, schema predisposto)

```sql
create table activity_baseline (
  subject_id     uuid    not null references subject(id) on delete cascade,
  hour_of_day    smallint not null,          -- 0..23 (in timezone del subject)
  metric         text     not null,          -- 'quiet_gap' | 'steps' | ...
  mean_value     real,
  stddev_value   real,
  sample_count   integer  not null default 0,
  updated_at     timestamptz not null default now(),
  primary key (subject_id, hour_of_day, metric)
);
```

## Check-in ed escalation

### `checkin_request` — richiesta on-demand

```sql
create table checkin_request (
  id             uuid        primary key default gen_random_uuid(),
  subject_id     uuid        not null references subject(id) on delete cascade,
  requested_by_user_id uuid  not null references app_user(id),
  status         text        not null default 'pending',  -- pending|partial|answered|timed_out|failed
  requested_at   timestamptz not null default now(),
  partial_at     timestamptz,               -- quando sono arrivati i segnali telefono
  answered_at    timestamptz,               -- quando è arrivato il battito fresco
  result         jsonb       not null default '{}',  -- snapshot del bundle restituito
  created_at     timestamptz not null default now()
);
create index on checkin_request (subject_id, requested_at desc);
```

### `escalation_action` — un gradino invocato

```sql
create table escalation_action (
  id             uuid        primary key default gen_random_uuid(),
  subject_id     uuid        not null references subject(id) on delete cascade,
  checkin_id     uuid        references checkin_request(id),
  triggered_by_user_id uuid  not null references app_user(id),
  rung           smallint    not null,       -- 2..5
  action_type    text        not null,       -- 'force_sync'|'vibrate'|'ring'|'confirm_prompt'|'audio_out'|'audio_channel'
  status         text        not null default 'sent',  -- sent|delivered|executed|failed|cancelled
  params         jsonb       not null default '{}',
  sent_at        timestamptz not null default now(),
  executed_at    timestamptz,
  created_at     timestamptz not null default now()
);
create index on escalation_action (subject_id, created_at desc);
```

### `confirmation_response` — la risposta del subject al gradino 4

```sql
create table confirmation_response (
  id             uuid        primary key default gen_random_uuid(),
  escalation_id  uuid        not null references escalation_action(id) on delete cascade,
  subject_id     uuid        not null references subject(id) on delete cascade,
  response       text        not null,       -- 'im_ok' | 'need_help' | 'dismissed'
  responded_at   timestamptz not null,       -- occurred_at lato device
  received_at    timestamptz not null default now(),
  source         text        not null default 'phone'  -- 'phone' | 'watch'
);
```

`response='im_ok'` genera un `activity_event` Tier A con `confidence=1.0`;
`need_help` genera un `alert_event` rosso.

## Geofence e alert

### `geofence`

```sql
create table geofence (
  id          uuid        primary key default gen_random_uuid(),
  subject_id  uuid        not null references subject(id) on delete cascade,
  name        text        not null,          -- 'Casa', 'Casa della figlia'
  center_lat  double precision not null,
  center_lon  double precision not null,
  radius_m    real        not null,
  kind        text        not null default 'safe',  -- 'safe' | 'alert'
  created_at  timestamptz not null default now()
);
```

### `alert_rule` — regole lato server (soglie, assenza dati, geofence)

```sql
create table alert_rule (
  id          uuid        primary key default gen_random_uuid(),
  subject_id  uuid        not null references subject(id) on delete cascade,
  rule_type   text        not null,   -- 'no_data'|'hr_range'|'geofence_exit'|'battery_low'|'quiet_too_long'
  params      jsonb       not null default '{}',  -- soglie, geofence_id, fasce orarie
  severity    text        not null default 'amber', -- 'amber' | 'red'
  enabled     boolean     not null default true,
  created_at  timestamptz not null default now()
);
```

> **Nota anti-falso-allarme:** una regola `no_data` può generare al massimo
> severità **ambra**, mai rossa (vedi [`03`](03-liveness-model.md), regola 1). Il
> vincolo è applicato in codice, non solo per convenzione.

### `alert_event` — alert scattati

```sql
create table alert_event (
  id           uuid        primary key default gen_random_uuid(),
  subject_id   uuid        not null references subject(id) on delete cascade,
  rule_id      uuid        references alert_rule(id),
  severity     text        not null,   -- 'amber' | 'red'
  title        text        not null,
  detail       jsonb       not null default '{}',
  occurred_at  timestamptz not null,
  created_at   timestamptz not null default now(),
  acknowledged_by_user_id uuid references app_user(id),
  acknowledged_at timestamptz
);
create index on alert_event (subject_id, created_at desc);
```

## Push e audit

### `push_token` — token per notificare i caregiver (Web Push / FCM)

```sql
create table push_token (
  id          uuid        primary key default gen_random_uuid(),
  user_id     uuid        not null references app_user(id) on delete cascade,
  kind        text        not null,   -- 'web_push' | 'fcm'
  token       text        not null,
  created_at  timestamptz not null default now(),
  unique (user_id, token)
);
```

### `audit_log` — chi ha visto o fatto cosa

```sql
create table audit_log (
  id          bigserial   primary key,
  subject_id  uuid        references subject(id) on delete set null,
  actor_user_id uuid      references app_user(id),
  actor_kind  text        not null,   -- 'user' | 'device' | 'system'
  action      text        not null,   -- 'view_location'|'checkin'|'escalate:alarm'|'grant:create'|...
  target      text,                    -- risorsa toccata
  meta        jsonb       not null default '{}',
  occurred_at timestamptz not null default now()
);
create index on audit_log (subject_id, occurred_at desc);
create index on audit_log (actor_user_id, occurred_at desc);
```

L'`audit_log` è **consultabile dal subject** nella propria app: è il registro che
rende la scala di escalation difendibile (vedi [`07`](07-authorization-privacy.md)).

## Riepilogo tabelle

| Tabella | Tipo | Volume | Note |
|---------|------|--------|------|
| `app_user` | dominio | basso | account |
| `subject` | dominio | basso | 1 in fase 1 |
| `device` | dominio | basso | collector + watch |
| `grant` | dominio | basso | autorizzazioni |
| `activity_event` | stream | **alto** | append-only, idempotente |
| `location_fix` | stream | **alto** | append-only, idempotente |
| `liveness_snapshot` | derivato | 1/subject | riscritto a ogni ingest |
| `activity_baseline` | derivato | basso | futuro |
| `checkin_request` | dominio | medio | on-demand |
| `escalation_action` | dominio | medio | gradini 2–5 |
| `confirmation_response` | dominio | basso | risposte "sto bene" |
| `geofence` | dominio | basso | zone |
| `alert_rule` / `alert_event` | dominio | basso/medio | regole e scatti |
| `push_token` | dominio | basso | notifiche caregiver |
| `audit_log` | log | medio | trasparenza |
