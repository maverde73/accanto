# 11 — Roadmap

Fasi incrementali. Ognuna produce qualcosa di **usabile end-to-end**, non un layer
orizzontale a metà. L'ordine massimizza il valore precoce e mette davanti le
verifiche che possono invalidare il disegno.

## Fase 0 — Design e documentazione ✅ (in corso)

- [x] Analisi dei vincoli hardware (watch non programmabile, verifiche sul device)
- [x] Modello di presenza a tre orologi
- [x] Scala di escalation a 5 gradini
- [x] Modello dati e API
- [x] Modello autorizzazioni + inquadramento privacy
- [x] Documentazione (questo insieme di file)

## Fase 0.5 — Verifiche sul dispositivo (BLOCCANTI, prima di scrivere codice serio)

Sono spike di poche ore ciascuno; il loro esito può cambiare il piano.

| # | Verifica | Se fallisce |
|---|----------|-------------|
| V1 | Aprire Mi Fitness **scrive HR fresco in Health Connect** entro ~30–60s? | il check-in gradino 2 va ripensato (o BLE in fase 2) |
| V2 | Lanciare Mi Fitness in foreground **dal background** funziona a schermo bloccato/spento? | serve strategia alternativa (es. tenere lo schermo, o accettare il limite) |
| V3 | Granularità reale dei campioni HR con "Monitoraggio continuo" a 1 min | dimensiona i trend e le finestre `FRESH_C` |
| V4 | Il watch **specchia** una notifica del collector (vibrazione al polso)? | gradino 3 dal polso non disponibile; resta il telefono |
| V5 | La **dismissione** di una notifica dal watch propaga al telefono? | niente "sto bene" dal polso; resta il telefono |
| V6 | Il Watch 6 ha **altoparlante/microfono**? | irrilevante: audio resta sul telefono |

> V1 e V2 sono le due che reggono l'intero valore del check-in on-demand: farle per
> prime.

## Fase 1 — MVP verticale (il cuore utile)

Obiettivo: **rispondere a "come sta ora?"** con presenza + check-in + mappa, per
1 subject e pochi caregiver.

**Backend**
- Schema + migrazioni (subset: subject, device, grant, activity_event,
  location_fix, liveness_snapshot, checkin_request, audit_log)
- Ingest idempotente + LivenessEngine + snapshot
- Auth (device token + JWT caregiver) + grant con scope base
- Realtime hub
- Command channel + FCM (solo `force_sync`, `location_live_on/off`)

**Collector**
- Foreground service + outbox Room + uploader resiliente
- Sorgenti: interazione, attività, batteria, BT, GPS (idle/live)
- Health Connect reader (HR, passi)
- Check-in gradino 2 (force_sync) con risposta progressiva
- **Permission Dashboard** (fin da subito: è ciò che tiene vivo il sistema)

**Viewer**
- Dashboard presenza (headline + 3 orologi)
- Check-in "Come sta?" progressivo
- Mappa live + geofence base

**Esce quando:** un caregiver vede lo stato, preme "Come sta?", ottiene battito
fresco e posizione, e la persona compare sulla mappa.

## Fase 2 — Escalation e alert

- Gradini 3–5 (vibrazione/mirroring, allarme + conferma "sto bene", canale audio
  annunciato) — nei limiti di V4/V5/V6
- AlertEngine: `no_data` (ambra), `geofence_exit`, `battery_low`,
  `quiet_too_long`
- Web Push ai caregiver
- Audit log consultabile dal subject + consenso alla scala nel setup del collector
- Scope estesi (`escalation:*`, `location:coarse`)

## Fase 3 — Intelligenza e rifinitura

- `activity_baseline` per fascia oraria ("silenziosa da 3h, normale per quest'ora")
- Trend e storico ricchi nel viewer
- Retention/aggregazione automatica + export dati (portabilità)
- Consapevolezza notte/giorno completa nelle finestre e negli alert
- Hardening: rate limit, cifratura colonna vitali, osservabilità

## Fase 4 — (Opzionale, da valutare) BLE diretto

Solo se le verifiche mostrano che Health Connect non basta per un requisito reale
(es. latenza inaccettabile anche col sync forzato).

- Prerequisito: supporto del Redmi Watch 6 in Gadgetbridge o protocollo noto
- Consapevolezza dei costi: ruba la connessione a Mi Fitness, si rompe a ogni
  firmware, auth key legata all'account
- Abiliterebbe: HR più frequente, batteria watch reale, forse avvisi più rapidi

## Principi di esecuzione

- **TDD** per la logica di dominio (LivenessEngine, idempotenza, invarianti
  anti-falso-allarme).
- Ogni fase **deployabile** e testata end-to-end prima della successiva.
- Le verifiche di Fase 0.5 **prima** del codice che ci si appoggia sopra.
- Nessun falso allarme: le invarianti di [`03`](03-liveness-model.md) hanno test di
  regressione dedicati.
