# 10 — Viewer web

L'interfaccia del caregiver. **Web, non app installabile.**

## Perché web

- Per lo scopo "chiunque io autorizzi", un **link** è più semplice da distribuire
  *e da revocare* di un APK.
- Nessuno store, nessun aggiornamento forzato, nessuna frammentazione di
  piattaforma: i caregiver possono essere su Android, iPhone, desktop.
- La revoca di un grant taglia l'accesso immediatamente, senza disinstallazioni.

## Stack

| Ambito | Scelta |
|--------|--------|
| Framework | Next.js (App Router) + TypeScript strict |
| UI | componenti accessibili, mobile-first |
| Mappa | **MapLibre GL** + tile **OpenStreetMap** (no API key, no costi, self-hostabile) |
| Realtime | WebSocket (SSE fallback) verso il backend |
| Stato server | React Query / SWR (fetch + cache + invalidazione su realtime) |
| Notifiche | Web Push (VAPID) per gli alert |
| Auth | sessione JWT, refresh silenzioso |

## Schermate

### 1. Dashboard presenza (la home)

Il pannello che risponde a "come sta ora?" in tre secondi.

```
┌─────────────────────────────────────────┐
│  Anna                          🟢 Attiva │
│  alle 12:34 · ha sbloccato il telefono   │
│                                          │
│  🚶 si muove dalle 12:31                 │
│  ❤️ battito 72 · 12:40                   │
│  🔋 telefono 88% · ⌚ in uso             │
│                                          │
│  [ Come sta? ]        [ Sulla mappa → ]  │
└─────────────────────────────────────────┘
```

- **Headline** con colore semantico (verde/ambra/grigio/rosso — vedi
  [`03`](03-liveness-model.md)); i **tre orologi** sempre visibili sotto.
- Timestamp mostrati come "N minuti fa" **basati su `occurred_at`**, mai sul
  momento della risposta HTTP.
- Il colore **grigio** ("non so") ha un micro-testo che spiega perché ("nessun dato
  da 34 min · probabilmente in carica") e rimanda al pannello salute — non allarma.

### 2. Check-in ed escalation

- Pulsante **"Come sta?"** → avvia il check-in; UI a **risposta progressiva**:
  1. spinner "Richiesta inviata…"
  2. riga verde con i segnali telefono (~secondi)
  3. riga con il battito fresco (~decine di secondi)
- **Scala di escalation** presentata come gradini crescenti, ognuno con
  un'etichetta chiara di invasività e visibile solo se il caregiver ha lo scope:
  - *Fai vibrare il polso* (`escalation:notify`)
  - *Chiedi conferma "stai bene?"* (`escalation:alarm`)
  - *Apri canale audio* (`escalation:audio`)
- Ogni azione mostra lo **stato** (inviato → eseguito → risposta) via realtime, e
  finisce nell'audit.

### 3. Mappa live

- Pallino live con **cerchio di accuratezza** (non fingere precisione: al chiuso il
  fix degrada).
- Scia dell'ultimo tratto; timestamp dell'ultimo fix.
- **Geofence** disegnate ("Casa", "Casa della figlia"); stato "è a casa / è uscito".
- Aprire la mappa attiva il **live mode** lato collector (GPS preciso); chiuderla lo
  disattiva → risparmio batteria del subject.
- Con scope `location:coarse`: nessun pallino preciso, solo la zona/geofence (il
  backend non invia il dato fine).

### 4. Storico e trend

- Timeline degli eventi (Tier A/B/C/D) e dei check-in/escalation.
- Grafici dei vitali (battito nel tempo, sonno), medie notturne, andamento
  settimanale.
- Richiede scope `history`.

### 5. Amministrazione (owner)

- Gestione **grant**: crea/modifica/revoca, con scope e scadenza (UI che rende
  leggibili i casi di [`07`](07-authorization-privacy.md)).
- Gestione **geofence** e **alert-rule**.
- **Audit log** consultabile.

## Realtime e coerenza

- Un canale WS per subject; i messaggi (`snapshot`, `location`, `checkin`,
  `escalation`, `alert`) aggiornano la cache di React Query senza refetch.
- Il canale rispetta gli **scope**: niente messaggi `location` senza permesso;
  `coarse` arriva arrotondato dal server.
- Riconnessione automatica con backoff; on reconnect, refetch dello snapshot.

## Accessibilità e chiarezza

Il caregiver può essere non tecnico e in ansia. Regole:

- **Colore + testo + icona** (mai colore da solo): daltonismo e chiarezza.
- Linguaggio naturale, niente gergo ("ha usato il telefono da poco", non
  "last_interaction 12:34Z").
- Lo stato **grigio non deve spaventare**: è "non so", spiegato, non "allarme".
- Il **rosso è raro e serio**: riservato a `need_help` e regole critiche esplicite.

## Notifiche al caregiver

- Web Push per gli `alert_event` (ambra/rossi) secondo gli scope.
- Deep-link dalla notifica alla schermata pertinente (snapshot / mappa / alert).
- Impostazioni per silenziare le ambre e tenere solo le rosse.

## Distribuzione e onboarding

- Il caregiver riceve un **invito** (link) dall'owner; accede, e vede solo i
  subject e gli scope concessi.
- Nessuna installazione. Su mobile, "Aggiungi a schermata Home" (PWA) è opzionale
  per l'accesso rapido e le push.
