# 08 — Collector Android

L'app sul telefono del subject. È il componente tecnicamente più delicato: da esso
dipende se il sistema funziona ancora tra tre mesi.

## Perché nativo (Kotlin), non Flutter

Lo stack del team include Flutter, ma qui è la scelta sbagliata. Il collector vive
di:

- **foreground service persistente** che sopravvive a Doze e all'aggressività di
  One UI;
- **Health Connect** client;
- **permessi speciali** e loro verifica continua;
- **avvio di activity dal background**, `NotificationListener`/notifiche di sistema,
  full-screen intent, stream audio ALARM.

Sono tutte aree dove i plugin cross-platform sono fragili o assenti e dove il
nativo Android è di prima classe. Il costo di un bridge affidabile supererebbe il
risparmio. → **Kotlin + Jetpack.**

## Componenti

```
app/
 ├─ CollectorForegroundService   ← il cuore: tiene vivo tutto
 ├─ sensors/
 │   ├─ LocationSource           ← FusedLocationProvider (idle/live)
 │   ├─ ActivitySource           ← Activity Recognition API
 │   ├─ InteractionSource        ← ACTION_USER_PRESENT, screen on/off
 │   ├─ AppUsageSource           ← UsageStatsManager
 │   ├─ BatterySource            ← BatteryManager + broadcast
 │   └─ BtContactSource          ← stato connessione watch
 ├─ health/HealthConnectReader   ← HR, passi, sonno (changes token)
 ├─ queue/                       ← Room: outbox eventi + fix, idempotente
 ├─ net/Uploader                 ← batch upload, backoff, resilienza offline
 ├─ command/CommandExecutor      ← FCM → force_sync/vibrate/ring/confirm/audio
 ├─ escalation/                  ← notifiche, full-screen, ALARM stream, audio
 ├─ setup/PermissionDashboard    ← stato permessi + deep-link alle schermate
 └─ audit/ConsentStore           ← consenso alla scala, storico locale
```

## Modello di raccolta: event-driven, non polling

| Sorgente | Meccanismo | Costo |
|----------|-----------|-------|
| Sblocco / schermo | broadcast runtime | ~0 |
| Attività | Activity Recognition (transizioni) | basso (hardware) |
| Passi | step counter | ~0 (hardware) |
| Batteria / carica | broadcast | ~0 |
| Watch BT | callback stato | ~0 |
| GPS idle | spostamento significativo / balanced | basso |
| GPS live | high accuracy ~5s (solo su comando) | alto, temporaneo |
| Health Connect | polling con changes-token, cadenza moderata | basso |

In steady state il consumo è minimo. Diventa aggressivo (sync forzato, GPS preciso)
**solo** su check-in o mappa aperta.

## Coda locale e upload idempotente

- Ogni evento/fix è scritto **prima** in Room (outbox) con la sua `dedup_key`
  deterministica.
- L'`Uploader` invia in batch quando c'è rete; in offline accumula.
- Alla riconnessione **ritrasmette**: il backend fa upsert su `dedup_key`, quindi i
  duplicati sono innocui (specie i passi, che altrimenti si sommerebbero).
- Backoff esponenziale, WorkManager come rete di sicurezza per gli upload differiti.

## Il check-in (gradino 2) lato collector

```
FCM high-priority "force_sync" arriva (sveglia da Doze)
 → GET /commands/{id} (valida)
 → RACCOLTA IMMEDIATA segnali telefono → POST /ingest/events (risposta parziale)
 → lancia Mi Fitness in foreground (SYSTEM_ALERT_WINDOW)
 → attende/pollng Health Connect per un campione HR fresco (timeout ~90s)
 → POST /ingest/events con HR → POST /commands/{id}/ack
```

**Rischio tecnico da validare sul campo:** comportamento a schermo bloccato/spento
quando si lancia Mi Fitness. È il punto più incerto dell'intero disegno.

## Escalation lato collector

| Gradino | Implementazione |
|---------|-----------------|
| 3 vibrate | notifica di sistema (il watch la specchia via Mi Fitness) + `VibratorManager` |
| 4 ring | `AudioManager` su **stream ALARM** (batte silenzioso/DND) |
| 4 confirm | full-screen intent / activity con azioni `im_ok` / `need_help` |
| 5 audio_out | riproduzione messaggio/TTS su stream ALARM |
| 5 audio_channel | annuncio vocale + apertura microfono (notifica persistente obbligatoria) + WebRTC |

Le risposte del subject (`im_ok`/`need_help`/dismiss) tornano via
`POST /commands/{id}/response`.

## Permessi richiesti

### Runtime (dialog in-app, raggruppabili)

- `ACCESS_FINE_LOCATION` (+ `ACCESS_COARSE_LOCATION`)
- `ACCESS_BACKGROUND_LOCATION` — **su Android 11+ va chiesto in un secondo momento**
  e concesso come "Consenti sempre" da Impostazioni, non insieme agli altri
- `ACTIVITY_RECOGNITION`
- `POST_NOTIFICATIONS` (Android 13+)
- `BLUETOOTH_CONNECT` / dispositivi vicini
- `RECORD_AUDIO` (solo se si abilita il gradino 5 in ingresso)
- lettura Health Connect (HR, passi, sonno) — permessi dedicati Health Connect

### Speciali (schermate di sistema separate, NON raggruppabili da un dialog)

- **Visualizza sopra altre app** (`SYSTEM_ALERT_WINDOW`) — avvio activity dal
  background, full-screen
- **Accesso all'uso** (`PACKAGE_USAGE_STATS`) — UsageStats
- **Notifiche a tutto schermo** (`USE_FULL_SCREEN_INTENT`, Android 14+)
- **Accesso Non disturbare** (`ACCESS_NOTIFICATION_POLICY`) — riserva per il ring
  in DND
- **Batteria "Senza restrizioni"** — esenzione Doze
- (Config in altre app) **Health Connect**: collegamento e concessione dati
- (Config in altre app) **Mi Fitness**: abilitare le notifiche del collector nel
  mirroring verso il watch

> ⚠️ Android ha abolito i permessi "all'installazione" nel 2015. Non esiste un modo
> per farli accettare tutti in un colpo dall'installer. Il massimo accorpabile è il
> gruppo runtime *normale*; gli speciali sono uno-per-schermata.

## Setup via ADB (la "strada d'oro" quando si ha il telefono in mano)

Con il debug USB attivo, la quasi totalità dei permessi speciali si concede da PC
in un unico script. Nomi esatti da verificare sull'S24 / versione di One UI.

```bash
PKG=com.tuo.collector

# runtime
adb shell pm grant $PKG android.permission.ACCESS_FINE_LOCATION
adb shell pm grant $PKG android.permission.ACCESS_BACKGROUND_LOCATION
adb shell pm grant $PKG android.permission.ACTIVITY_RECOGNITION
adb shell pm grant $PKG android.permission.POST_NOTIFICATIONS

# speciali (appops)
adb shell appops set $PKG SYSTEM_ALERT_WINDOW allow       # sopra altre app
adb shell appops set $PKG GET_USAGE_STATS allow           # uso app
adb shell appops set $PKG USE_FULL_SCREEN_INTENT allow    # Android 14+

# esenzione Doze / batteria
adb shell dumpsys deviceidle whitelist +$PKG
```

**Non** passano da ADB (sono config *dentro altre app*):

- collegamento **Health Connect**;
- abilitazione notifiche del collector nel **mirroring di Mi Fitness**;
- associazione dell'account nell'app.

Restano tre passaggi manuali, non venti.

## Permission Dashboard (requisito, non optional)

One UI o un aggiornamento possono **revocare** un permesso mesi dopo, e il sistema
smette di funzionare in silenzio. Serve una schermata che:

1. elenca ogni permesso con stato ✅/❌;
2. per ciascuno, un tap che porta **direttamente** alla schermata di sistema
   giusta;
3. **ricontrolla periodicamente** (all'avvio del service e su schedule) e, se
   qualcosa è saltato, **notifica il subject e/o l'owner** ("Accanto non può più
   accedere alla posizione").

Il collector invia lo stato permessi al backend nell'heartbeat
(`permissions_ok`), così la salute pipeline lo riflette. Questa schermata è
facilmente il ~20% del lavoro sul collector, ed è ciò che decide la longevità del
sistema.

## Convivenza con Mi Fitness

- **Una sola connessione BLE al watch.** Non tentiamo BLE diretto: la connessione
  resta a Mi Fitness. Noi leggiamo da Health Connect e usiamo Mi Fitness come
  gateway (sync forzato, mirroring notifiche).
- Il collector **non** deve uccidere né interferire con Mi Fitness; lo lancia solo
  in foreground per forzare i sync.

## Configurazione del telefono (a carico dell'utente)

Il subject/owner cura la configurazione OEM (batteria senza restrizioni, no deep
sleep, no revoca automatica permessi, autostart). Riferimento per i pattern
per-produttore: `dontkillmyapp.com/samsung`. Il collector **verifica** questa
configurazione ma non può imporla: da qui l'importanza della Permission Dashboard.
