# Accanto

> Sistema di monitoraggio di presenza e benessere per una persona cara, costruito
> attorno a un **Redmi Watch 6 (M2523W1)** e allo smartphone che la persona porta
> sempre con sé.

**Il nome "Accanto" è provvisorio.** Compare solo qui, nei titoli della
documentazione e come `appName` di default: cambiarlo è un find/replace.

---

## Il problema in una frase

> *"La persona non mi risponde al telefono. Vediamo come sta."*

Accanto risponde a questa domanda nel modo meno invasivo possibile, e — se serve —
permette di salire una **scala di azioni progressive** fino ad avere certezza.

## Perché esiste (e perché è fatto così)

Il Redmi Watch 6 **non è programmabile**: gira Xiaomi Vela (RTOS proprietario),
non Wear OS. Non si installano app sul polso, non c'è un SDK pubblico, non si
accede ai sensori. Il watch è quindi una **sorgente di dati**, non un computer su
cui girare codice.

Di conseguenza tutta l'intelligenza vive sul **telefono** (che invece è
completamente programmabile) e a valle di esso. Questa non è una scelta di
comodità: è l'unica architettura possibile con questo hardware. La motivazione
completa è in [`docs/02-device-constraints.md`](docs/02-device-constraints.md).

## Cosa fa

- **Stato di presenza a colpo d'occhio** — un modello a "tre orologi"
  (interazione / movimento / segni vitali) che distingue *"attiva"* da *"ferma"*
  da *"non ho dati"*, senza mai spacciare l'assenza di dati per un allarme.
  Vedi [`docs/03-liveness-model.md`](docs/03-liveness-model.md).
- **Check-in on-demand** — il caregiver chiede "come sta?" e il sistema forza un
  aggiornamento (posizione fresca + sync del battito dal watch) in secondi/minuti.
- **Scala di escalation a 5 gradini** — dalla lettura passiva fino all'allarme a
  tutto schermo con conferma *"sto bene"* e al canale audio annunciato.
  Vedi [`docs/04-escalation-ladder.md`](docs/04-escalation-ladder.md).
- **Mappa in tempo reale** con geofence ("è a casa", "è uscito").
- **Autorizzazioni granulari, con scadenza e revoca**, e un audit log di chi ha
  visto o fatto cosa. Vedi [`docs/07-authorization-privacy.md`](docs/07-authorization-privacy.md).

## Cosa NON fa (limiti onesti)

- **Non dà alert cardiaci istantanei.** Gli avvisi 120/50 BPM del watch restano
  nel firmware e non generano notifiche sul telefono (verificato sul dispositivo).
  Il battito arriva a batch, con la latenza del sync di Mi Fitness.
- **Non traccia la persona, traccia il telefono.** Se il telefono è spento,
  scarico o lontano, la catena si interrompe. Nel nostro scenario la persona porta
  sempre il telefono con sé, ma il limite resta strutturale.
- **Non accede ai sensori grezzi del watch** (accelerometro, GPS live): Vela non
  li espone da nessuna via, nemmeno via BLE.
- **Non ascolta di nascosto.** L'audio in ingresso è possibile ma sempre
  annunciato: Android impone notifica persistente e indicatore quando il microfono
  è attivo, e il design lo abbraccia invece di aggirarlo.

## Architettura in tre pezzi

```
  ┌───────────┐  BLE   ┌───────────────────┐  HTTPS/FCM  ┌──────────┐  WS/HTTPS ┌──────────┐
  │  Watch    │ ─────▶ │  Telefono S24     │ ──────────▶ │ Backend  │ ────────▶ │ Viewer   │
  │ (sorgente)│        │  Mi Fitness +     │ ◀────────── │ FastAPI  │ ◀──────── │ web app  │
  └───────────┘        │  Collector Accanto│    comandi  │ + Postgres│  comandi  │(caregiver)│
                       └───────────────────┘             └──────────┘           └──────────┘
```

1. **Collector** (Android nativo, Kotlin) — legge Health Connect + sensori del
   telefono, esegue i comandi del caregiver (sync forzato, escalation), fa upload
   resiliente all'offline. Vedi [`docs/08-collector-android.md`](docs/08-collector-android.md).
2. **Backend** (FastAPI + Postgres) — ingest idempotente, calcolo dello stato di
   presenza, autorizzazioni, canale comandi, realtime verso i viewer.
   Vedi [`docs/09-backend.md`](docs/09-backend.md).
3. **Viewer** (Next.js web app) — dashboard, mappa, escalation. Nessun APK da
   distribuire: un link che si autorizza e si revoca.
   Vedi [`docs/10-viewer-web.md`](docs/10-viewer-web.md).

## Indice della documentazione

| # | Documento | Contenuto |
|---|-----------|-----------|
| 00 | [Overview](docs/00-overview.md) | Visione, scenario, scopo, non-obiettivi |
| 01 | [Architettura](docs/01-architecture.md) | Componenti, flussi dati, scelte tecnologiche |
| 02 | [Vincoli del dispositivo](docs/02-device-constraints.md) | Cosa è accessibile dal watch e dal telefono, e perché |
| 03 | [Modello di presenza](docs/03-liveness-model.md) | I tre orologi, regole di fusione, stati |
| 04 | [Scala di escalation](docs/04-escalation-ladder.md) | I 5 gradini, check-in, azioni remote |
| 05 | [Modello dati](docs/05-data-model.md) | Schema SQL completo |
| 06 | [API](docs/06-api.md) | REST + realtime + canale comandi |
| 07 | [Autorizzazioni e privacy](docs/07-authorization-privacy.md) | Grant, revoca, audit, GDPR |
| 08 | [Collector Android](docs/08-collector-android.md) | Permessi, servizi, setup via ADB |
| 09 | [Backend](docs/09-backend.md) | FastAPI, layer, deployment |
| 10 | [Viewer web](docs/10-viewer-web.md) | Next.js, mappa, realtime |
| 11 | [Roadmap](docs/11-roadmap.md) | Fasi e milestone |
| 12 | [Glossario](docs/12-glossary.md) | Termini |

## Stato

**Fase 0 — documentazione e design.** Nessun codice applicativo ancora scritto.
La roadmap in [`docs/11-roadmap.md`](docs/11-roadmap.md) definisce le fasi
successive.

## Nota legale, in breve

Battito cardiaco e posizione sono **dati sanitari e di localizzazione**, categoria
particolare ex art. 9 GDPR. Finché l'uso è strettamente personale/familiare vale
l'esenzione domestica; nel momento in cui il sistema viene aperto a terzi, non
vale più. Il consenso informato della persona monitorata è un prerequisito, non
una formalità. Dettagli in [`docs/07-authorization-privacy.md`](docs/07-authorization-privacy.md).
