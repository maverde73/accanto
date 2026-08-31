# Accanto — collector

App Android sul telefono della persona monitorata. Kotlin + Jetpack Compose.

Progetto: [`../README.md`](../README.md) · design:
[`../docs/08-collector-android.md`](../docs/08-collector-android.md).

## Stato

Raccoglie, accoda e invia. Ci sono foreground service, outbox Room, uploader
resiliente, le quattro sorgenti di segnale, pairing e permission dashboard.
**58 test unitari passano** e l'APK debug si costruisce.

**Non c'è ancora** l'esecuzione dei comandi (sync forzato di Mi Fitness e i
gradini 3-5) né le schermate complete dal mockup.

## Pairing

Il collector nasce senza credenziali. Il flusso:

1. Chi amministra crea il device dal backend
   (`POST /v1/subjects/{id}/devices`) e ottiene un **codice a 8 caratteri**.
2. La persona monitorata lo digita **sul proprio telefono**.
3. Il collector lo scambia con un token (`POST /v1/devices/pair`).

La separazione fra codice e token non è cosmetica. Il codice lo digita una
persona, quindi deve essere corto — e per questo è **monouso, valido 15 minuti
e con rate limit**. Il token non lo digita nessuno, quindi può essere lungo.

L'alfabeto del codice esclude `0/O` e `1/I/L`: viene letto ad alta voce o
ricopiato a mano, e un carattere sbagliato è una telefonata di assistenza, non
una misura di sicurezza.

È anche il punto in cui il consenso diventa concreto: **nessuno può arruolare
questo telefono da remoto.**

## Build

```bash
export JAVA_HOME=~/.jdks/jdk-17.0.19+10
export ANDROID_HOME=~/Android
./gradlew :app:testDebugUnitTest
./gradlew :app:assembleDebug
```

`local.properties` non è versionato: contiene il percorso locale dell'SDK.

In debug l'app punta a `http://10.0.2.2:8000` (l'host visto dall'emulatore); in
release a `https://api.accanto.maurizioverde.info`. Vedi
[`../docs/13-deployment.md`](../docs/13-deployment.md).

## Perché Kotlin nativo e non Flutter

Il collector vive di foreground service persistente, Health Connect, permessi
speciali, avvio di activity dal background, full-screen intent e stream audio
ALARM. Sono tutte cose che in Flutter si scrivono **comunque in Kotlin**, dietro
un platform channel: il bridge sarebbe costo aggiunto, non risparmiato.

## Il contratto con il backend è verificato, non dichiarato

`DedupKey` deve produrre **esattamente** la stessa stringa di
`backend/app/domain/dedup.py`: se le due implementazioni divergono, ogni evento
ritrasmesso dopo una disconnessione viene salvato due volte e i passi si
gonfiano.

Il test `keys match the backend byte for byte` confronta con valori calcolati
dal backend Python, e il suo fallimento su un valore alterato è stato verificato
apposta — un test di contratto che non sa fallire non è un test.

## Decisioni già prese nel codice

- **`SCREEN_ON` è Tier D, non interazione.** Una notifica o il lift-to-wake
  accendono lo schermo senza che nessuno tocchi il telefono: contarlo come
  interazione produrrebbe un rassicurante «in attività» generato da nessuno.
- **Il debounce sta qui, non nel backend.** Le chiavi di dedup usano finestre
  fisse allineate all'epoch, che tollerano i doppioni ravvicinati ma non li
  eliminano di sicuro. Solo il collector conosce l'evento precedente.
- **Tre canali di notifica separati**, così la persona può silenziare un avviso
  discreto senza silenziare anche quello che conta.
- **Nessun backup né trasferimento su nuovo telefono**: l'outbox contiene dati
  sanitari e di posizione e il token del device è una credenziale viva. Il
  ri-accoppiamento su un telefono nuovo è la strada corretta.

## Dispositivo di riferimento

Verificato su **SM-S928B (Galaxy S24 Ultra), Android 16, API 36**:

- Mi Fitness è `com.xiaomi.wearable` — confermato sul dispositivo, non assunto;
- Health Connect è quello integrato di sistema
  (`com.google.android.healthconnect.controller`).

`compileSdk`/`targetSdk` sono a 35 mentre il telefono è API 36: da alzare, ma
solo dopo aver verificato la compatibilità di AGP, un cambiamento alla volta.
