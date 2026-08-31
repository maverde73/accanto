# 02 — Vincoli del dispositivo

Questo documento è la base fattuale di tutte le scelte architetturali. Se un domani
si cambia hardware, si riparte da qui.

## Il watch: Redmi Watch 6 (M2523W1)

### Sistema operativo

Gira **Xiaomi Vela**, un RTOS proprietario basato su NuttX (brandizzato come
"HyperOS for wearables"), **non Wear OS**. Conseguenze dirette:

- **Non si installano app di terze parti** sul watch.
- **Non esiste un SDK pubblico globale.** Il programma "quick app" di Vela è di
  fatto limitato al mercato cinese, con approvazione e firma Xiaomi.
- Il watch è una **scatola nera**: espone solo ciò che Mi Fitness decide di
  sincronizzare.

### Cosa si può ottenere dal watch (e come)

| Dato | Via | Latenza | Note |
|------|-----|---------|------|
| Frequenza cardiaca | Health Connect (batch) | minuti | Granularità = intervallo di "Monitoraggio continuo" |
| Passi | Health Connect | batch | |
| Sonno | Health Connect | batch (mattina) | |
| SpO2 / stress | Health Connect (se esportati) | batch | Da verificare che Mi Fitness li scriva |
| GPS | ❌ solo traccia di allenamento, a posteriori | — | **Non** disponibile live, nemmeno via BLE |
| Accelerometro grezzo | ❌ mai | — | Non esposto da nessuna via |
| Batteria del watch | ❌ non via Health Connect | — | Solo via BLE diretto; noi la **inferiamo** |
| Avvisi HR (120/50 BPM) | ❌ restano nel firmware | — | **Non** generano notifica sul telefono (verificato) |

### Verifiche già fatte sul dispositivo

- **Avvisi cardiaci → notifica telefono?** ❌ No. Impostando una soglia bassa e
  superandola, il watch vibra ma **non** compare alcuna notifica sul telefono. Gli
  avvisi 120/50 BPM vivono e muoiono nel firmware. → L'idea di intercettarli con un
  `NotificationListenerService` è **scartata**.
- **Monitoraggio continuo HR**: di default è impostato su "Intelligente"
  (campionamento rado e imprevedibile). Va portato a intervallo fisso (1–5 min) per
  avere un flusso utile. È l'impostazione che determina la granularità del battito.

- **V1 — Aprire Mi Fitness scrive campioni HR freschi in Health Connect?** ✅ **Sì.**
  Il sync forzato funziona: è ciò che rende possibile il check-in on-demand
  (gradino 2). Il watch ha già il dato nel buffer, aprire l'app lo trasferisce.
- **V2 — Il sync funziona a schermo bloccato/spento?** ✅ **Sì.** Era il rischio
  tecnico principale dell'intero disegno: nello scenario reale il telefono è in
  tasca. Con questo, **il BLE diretto (fase 4) non è necessario.**

### Verifiche ancora aperte

Nessuna bloccante. Le rimanenti cambiano *cosa* possiamo offrire ai gradini 3-5,
non se il sistema sta in piedi:

- **"Trova dispositivo" / far vibrare il watch** esiste in Mi Fitness? (per
  l'escalation dal polso via mirroring notifiche)
- Il Watch 6 ha **altoparlante/microfono**? (il Watch 5 sì, per chiamate BT)
- Latenza reale del sync **in background** (2 ore, notte) — meno critica ora che
  il modello è on-demand.

## Il telefono: Samsung Galaxy S24 (Android)

È l'opposto del watch: **completamente programmabile**. È il vero sensore ricco
del sistema.

| Dato | Disponibile | API | Latenza |
|------|-------------|-----|---------|
| GPS live | ✅ | FusedLocationProvider | secondi, alta precisione |
| Accelerometro grezzo | ✅ | SensorManager | alta frequenza |
| Attività (fermo/cammina/veicolo) | ✅ | Activity Recognition API | secondi |
| Passi | ✅ | Step counter (hardware) | secondi |
| Sblocco / presenza utente | ✅ | `ACTION_USER_PRESENT`, UsageStats | secondi |
| Schermo on/off | ✅ | broadcast | secondi |
| Batteria del telefono | ✅ | BatteryManager | continua |
| In carica (telefono) | ✅ | broadcast | continua |
| Watch connesso in BT | ✅ | BluetoothAdapter | continua |
| Frequenza cardiaca | ❌ | (solo via watch → Health Connect) | — |
| Sonno | ❌ | (solo via watch) | — |

### La gerarchia dei segnali (contro-intuitiva)

Il battito **non** è il dato più informativo per "come sta ora?". In ordine di
forza per lo scenario caregiver:

1. **Ultimo sblocco del telefono** — prova che la persona è cosciente e capace.
   Costo energetico ~0.
2. **Activity Recognition** — `IN_VEHICLE` / `WALKING` spiegano da soli metà dei
   mancati risposta.
3. **Accelerometro del telefono** — distingue "telefono sul tavolo" da "in tasca di
   qualcuno che si muove".
4. **Watch connesso in BT** — la persona è entro ~10 m dal telefono.
5. **Poi** il battito, che conferma o smentisce.

I primi quattro sono tutti lato telefono, tutti real-time veri, tutti a costo quasi
nullo, e **nessuno dipende dal sync di Mi Fitness**. È questa gerarchia che rende
possibile una risposta **progressiva** (vedi [`03`](03-liveness-model.md) e
[`04`](04-escalation-ladder.md)).

## Le strade scartate (e perché)

| Strada | Perché scartata |
|--------|-----------------|
| App sul watch | Vela non è programmabile |
| BLE diretto reverse-engineered | Protocollo cifrato, auth key legata all'account, ruba la connessione a Mi Fitness, si rompe a ogni firmware, ritardo mesi nel supporto ai modelli nuovi. Eventuale fase 2, non fase 1 |
| Cloud API Xiaomi | Non pubblica fuori dalla Cina |
| Intercettare avvisi HR via NotificationListener | Il watch non emette notifiche per gli avvisi cardiaci (verificato) |
| GPS del watch | Non disponibile live; il telefono lo sostituisce meglio |
| Accelerometro del watch (cadute) | Non esposto da nessuna via |

## Il ponte Mi Fitness non pubblica nulla — misurato

**Health Connect resta vuoto.** Non è una limitazione sul battito: Mi Fitness non
scrive **alcun** tipo di dato.

Survey eseguito dal collector sul dispositivo reale, 15 tipi su 7 giorni:

| Tipo | Record da Mi Fitness |
|------|----------------------|
| Battito, battito a riposo, variabilità HR | 0 |
| Passi, cadenza, distanza, velocità | 0 |
| Dislivello, piani saliti | 0 |
| Calorie attive e totali | 0 |
| Sonno, allenamenti | 0 |
| SpO2, frequenza respiratoria | 0 |

L'unico dato presente erano 5 record di passi del **contapassi del telefono**
(`com.android.healthconnect.phone.*`), non dell'orologio. Registrare l'origine e
non solo il conteggio è ciò che lo ha rivelato: prima erano stati attribuiti
all'orologio.

Verificato che i permessi non c'entrano: Mi Fitness ha `WRITE_HEART_RATE` e
`WRITE_STEPS` concessi, Accanto ha i corrispondenti `READ`, e nella schermata
"Autorizzazione dati" di Mi Fitness il collegamento risulta attivo. È autorizzato
e inerte.

### Alternative valutate, tutte chiuse

| Strada | Esito | Come verificato |
|--------|-------|-----------------|
| Health Sync e app ponte | leggerebbero da un Health Connect vuoto | ragionamento sulla catena |
| Cloud bridge Xiaomi (`mi_fitness_data_bridge`) | solo regione Cina, nessuna configurazione di regione; richiede credenziali dell'intero account | letto nel repository |
| Database locale di Mi Fitness | irraggiungibile: no root, `run-as` rifiutato, `ALLOW_BACKUP` assente | provato sul dispositivo |
| Export ufficiale GDPR | funziona, ma solo storico scaricato a mano | documentato da Xiaomi |
| SDK Vela / quick app | IDE solo Windows, distribuzione a firma controllata, supporto al modello ignoto; e i dati dovrebbero comunque tornare indietro passando per l'infrastruttura Xiaomi | documentazione Xiaomi |
| BLE diretto al watch | ruba l'unica connessione a Mi Fitness, si rompe a ogni firmware | valutazione, fase 4 |

**Conclusione:** su questo hardware la frequenza cardiaca non è ottenibile in
tempo reale. Il modello di presenza regge lo stesso, perché il battito è Tier C —
prova che una persona è viva, non che stia bene — e i segnali che valgono di più
vengono tutti dal telefono.

## Conseguenza di progetto

Il watch fornisce **battito e sonno a batch**; tutto il resto — real-time,
posizione, contesto, azioni — viene dal **telefono**. L'architettura di Accanto è
la conseguenza diretta di questa asimmetria, non una preferenza.
