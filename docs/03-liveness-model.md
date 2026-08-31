# 03 — Modello di presenza (liveness)

Il cuore del sistema. Traduce un flusso disordinato di segnali in una risposta che
un caregiver non tecnico capisce in tre secondi.

## Il problema

"Ultimo orario di attività" **non è un timestamp solo**. Se lo riduci a un unico
numero, un sussulto dell'accelerometro e uno sblocco del telefono finiscono a pari
merito, e il primo maschera l'assenza del secondo. Serve separare i segnali per
**cosa dimostrano**.

## I tre orologi (+ uno)

| Tier | Cosa prova | Segnali | Latenza |
|------|-----------|---------|---------|
| **A — Interazione** | La persona è **cosciente e capace**. Prova conclusiva. | sblocco (`ACTION_USER_PRESENT`), uso app (UsageStats), collegamento caricabatterie, **conferma "sto bene"** | secondi |
| **B — Movimento** | La persona **si muove**. Coscienza molto probabile. | Activity Recognition (`WALKING`/`IN_VEHICLE`), passi telefono, passi watch, spostamento GPS | secondi (telefono), minuti (watch) |
| **C — Segni vitali** | La persona è **viva**. Nulla sulla coscienza. | battito cardiaco valido | minuti |
| **D — Contatto di sistema** | Non prova nulla sulla persona. Serve a distinguere *"non ho dati"* da *"persona ferma"*. | watch connesso in BT, telefono acceso e raggiungibile | continua |

### L'ordine di forza è l'inverso dell'intuito

**Lo sblocco del telefono vale più del battito.** Un BPM di 68 è compatibile con
una persona che dorme, è svenuta o incosciente. Uno sblocco no: richiede volontà.
Tutta la macchina serve a stimare ciò che un pulsante "sto bene" dice con certezza.

## Regola di fusione → headline

Il sistema calcola quattro timestamp (uno per tier) e poi sceglie **una** headline:

```
last_interaction  = max(occurred_at) su eventi Tier A
last_movement     = max(occurred_at) su eventi Tier B
last_vital        = max(occurred_at) su eventi Tier C
last_contact      = max(occurred_at) su eventi Tier D

se   last_interaction  entro FRESH_A (default 15 min)  → "Attiva"                    verde
altr se last_movement  entro FRESH_B (default 15 min)  → "In movimento"             verde
altr se last_vital     entro FRESH_C (default 20 min)  → "Ferma, parametri normali" ambra
altr se last_contact   presente                        → "Silenziosa da N"          ambra
altr                                                   → "Nessun dato da N"         grigio
```

Le finestre `FRESH_*` sono configurabili per subject e **sensibili all'ora del
giorno** (vedi sotto). La headline mostra **un** orario, ma la UI tiene visibili
tutti e tre gli orologi:

> **Attiva** · alle 12:34
> _si muove dalle 12:31 · battito 72 alle 12:28 · telefono carico 88%_

Il caregiver vede in un colpo sia la risposta sia su cosa si basa.

## Le due regole non negoziabili

### 1. Assenza di dati NON è assenza di attività — e non è mai rossa

Watch in carica, telefono scarico, Mi Fitness ucciso da One UI: sono le cause di
gran lunga più frequenti di silenzio. Se colori di rosso un guasto della pipeline,
il caregiver impara a ignorare il rosso, e il giorno che serve non lo guarda.

| Colore | Significato | Quando |
|--------|-------------|--------|
| 🟢 verde | attività positiva recente | Tier A o B freschi |
| 🟡 ambra | so, ed è quieto / silenzio prolungato | solo Tier C, o solo Tier D |
| ⚪ grigio | **non so** (pipeline muta) | nessun tier recente |
| 🔴 rosso | **evidenza positiva di un problema** | solo da regole esplicite: es. conferma "aiuto", geofence critica, HR fuori range documentato a persona attiva |

Il rosso non nasce mai dall'*assenza* di qualcosa. Nasce solo dalla *presenza* di
un segnale negativo.

### 2. Mostra l'ora dell'evento, mai quella del sync

Un batch di campioni HR vecchi di 40 minuti che arriva adesso **non** deve
apparire come attività attuale. Due colonne distinte nel DB, `occurred_at` e
`received_at`; la UI usa **sempre** la prima. La seconda serve a te per misurare la
salute della pipeline (vedi "Salute della pipeline" sotto).

## Inferenza "watch probabilmente in carica"

Data l'assunzione *watch sempre indossato tranne in carica*:

```
se  nessun campione HR da > CHARGE_GAP (default 20 min)
    AND passi fermi nello stesso intervallo
→   watch_likely_charging = true
    UI: "probabilmente in carica (nessun dato da 34 min)"
```

Mai presentato come certezza. Se la ricarica ha un orario abituale, la confidenza
sale (il baseline lo apprende).

## Consapevolezza del contesto orario

Un'ora di silenzio alle 4 di notte e una alle 11 del mattino sono cose diverse. Di
notte:

- l'assenza di Tier A e B è **attesa**, non sospetta;
- il **Tier C diventa il segnale primario**;
- le finestre `FRESH_*` si allargano (una persona che dorme non sblocca il
  telefono).

### Baseline personale (funzione futura, schema predisposto ora)

Con qualche settimana di dati si passa da soglie fisse a un baseline per fascia
oraria:

> "Silenziosa da 3h, **normale per quest'ora** (media 2h40)."

Enormemente più informativo di un numero grezzo. La tabella `activity_baseline` è
già nello schema ([`05`](05-data-model.md)) anche se il calcolo arriva dopo.

## Salute della pipeline (meta-monitoraggio)

Un pannello separato, per il caregiver tecnico / owner, che **non** si confonde con
lo stato della persona:

- ritardo di ingest = `received_at − occurred_at` (P50/P90 nelle ultime 24h);
- ultimo contatto per ciascuna sorgente (telefono, watch);
- stato dei permessi del collector (vedi [`08`](08-collector-android.md));
- batteria di telefono (nota) e watch (inferita).

Se la pipeline è malata, lo stato della persona diventa **grigio**, non rosso, e il
pannello salute spiega perché.

## Debounce e igiene degli eventi

Gli sblocchi possono generare decine di eventi al minuto. Regole:

- **collasso** per tipo: max 1 evento ogni `DEBOUNCE_SECONDS` (default 30s) per
  coppia (kind, source);
- l'evento porta un **conteggio** nel payload, non N righe;
- gli eventi Tier D (contatto) sono heartbeat: 1 ogni pochi minuti basta.

Senza debounce la tabella `activity_event` esplode senza aggiungere informazione.

## Parametri configurabili (default)

| Parametro | Default | Descrizione |
|-----------|---------|-------------|
| `FRESH_A` | 15 min | finestra "interazione fresca" |
| `FRESH_B` | 15 min | finestra "movimento fresco" |
| `FRESH_C` | 20 min | finestra "vitali freschi" |
| `CHARGE_GAP` | 20 min | gap HR oltre cui si infer. ricarica |
| `DEBOUNCE_SECONDS` | 30 s | collasso eventi ripetuti |
| `NIGHT_START` / `NIGHT_END` | 23:00 / 07:00 | fascia notturna (allarga le finestre) |

Tutti overridabili per subject.
