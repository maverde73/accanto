# 04 — Scala di escalation

Le funzioni di contatto attivo non sono capacità separate: sono **i gradini di una
sola funzione**. Il caregiver sale solo finché non ottiene risposta. Ogni gradino è
più invasivo e più conclusivo del precedente, e la scala rende esplicito il
compromesso invece di nasconderlo.

## I 5 gradini

| # | Azione | Visibile al subject | Segnale ottenuto | Tecnologia |
|---|--------|---------------------|------------------|------------|
| 1 | Lettura passiva dello snapshot | no | inferenza | nessuna (già in DB) |
| 2 | **Check-in / sync forzato** | quasi no | battito fresco + segnali telefono | FCM → foreground Mi Fitness |
| 3 | **Notifica discreta** → il watch vibra | sì, discreta | conferma se risponde | notifica telefono + mirroring Mi Fitness |
| 4 | **Allarme pieno + "Stai bene?"** a tutto schermo | sì, forte | **certezza** se preme | full-screen intent + stream ALARM |
| 5 | **Canale audio annunciato** | sì, massima | valutazione diretta | FCM → audio / WebRTC |

## Gradino 1 — Lettura passiva

Nessuna azione sul telefono del subject. Il caregiver legge lo
`liveness_snapshot`. Nel caso comune la domanda finisce qui.

## Gradino 2 — Check-in on-demand (il più prezioso in rapporto costo/beneficio)

**Non ordina una misurazione: forza un sync.** Con il monitoraggio continuo a
1–5 min, il watch ha **già** un dato fresco nel buffer; il ritardo è nel
trasferimento watch → telefono. Quindi il check-in forza quel trasferimento.

### Catena tecnica

```
1. Caregiver preme "Come sta?"  → Backend crea checkin_request(status=pending)
2. Backend → push FCM HIGH-PRIORITY al collector
3. La push sveglia il collector anche in Doze (esenzione high-priority)
4. Il collector, IMMEDIATAMENTE, raccoglie i segnali telefono (unlock recente,
   activity, accel, GPS, batteria, watch BT) → li invia SUBITO (risposta parziale)
5. In parallelo lancia Mi Fitness in foreground (permesso SYSTEM_ALERT_WINDOW)
   → Mi Fitness sincronizza col watch → scrive HR fresco in Health Connect
6. Il collector legge l'HR fresco → lo invia (risposta completa)
7. Backend: checkin_request(status=answered) + snapshot; Realtime → Viewer
```

### Risposta progressiva

Il caregiver vede **prima** i segnali del telefono (secondi) e **poi** il battito
(decine di secondi / minuti):

> ⏱️ *Richiesta inviata…*
> ✅ *Telefono sbloccato 4 min fa · in movimento a piedi · watch connesso* — **~8 s**
> ✅ *Battito 72 · misurato 12:41* — **~50 s**

Nel 90% dei casi la prima riga chiude già la questione.

### Trucco del punto 5 (avvio activity dal background)

Android blocca l'avvio di activity dal background, **ma** concede un'esenzione
documentata alle app con `SYSTEM_ALERT_WINDOW` ("Visualizza sopra altre app").
Pesante da chiedere, ma molto più leggero di un AccessibilityService. Da
verificare sul campo il comportamento a schermo bloccato/spento (rischio tecnico
principale del disegno).

### Limiti

- Telefono spento/scarico/lontano → catena interrotta (posizione = dov'è il
  telefono).
- Il lancio di Mi Fitness è **visibile** sullo schermo del subject: va dichiarato
  nel setup. In un contesto di monitoraggio è trasparenza, non difetto.

## Gradino 3 — Notifica discreta (fa vibrare il polso)

Il watch **specchia le notifiche del telefono** se il collector è abilitato nel
mirroring di Mi Fitness. Quindi: **postare una notifica sul telefono** → il watch
vibra e mostra il testo. Non controlliamo il watch, controlliamo il telefono e il
watch segue. Molto più robusto che automatizzare "Trova dispositivo" con
Accessibility.

- Notifica con testo ("Tutto bene? Tocca per rispondere").
- **Vibrazione telefono**: `VibratorManager`, permesso normale, funziona in
  silenzioso.
- **Risposta dal polso (da verificare):** con `setDeleteIntent`, se il subject
  scarta la notifica dal watch, la dismissione *dovrebbe* propagarsi al telefono e
  far scattare l'intent → "ho visto, sto bene" senza tirare fuori il telefono. La
  sincronizzazione delle dismissioni sui watch Xiaomi è incostante: **test da
  fare**.

## Gradino 4 — Allarme pieno + conferma "sto bene"

**È la funzione più preziosa del progetto.** Un *"sto bene" premuto* è il segnale
Tier A più forte che esista: non è un'inferenza, è una dichiarazione.

- **Audio su stream ALARM**: le sveglie ignorano silenzioso, vibrazione e quasi
  ogni modalità Non disturbare. Non serve toccare le impostazioni audio della
  persona. (In riserva: `ACCESS_NOTIFICATION_POLICY` per i casi limite DND.)
- **Schermata a tutto schermo**: `USE_FULL_SCREEN_INTENT` (Android 14+ richiede
  concessione utente) oppure activity lanciata con `SYSTEM_ALERT_WINDOW`.
- **Pulsanti**: *"Sto bene"* / *"Ho bisogno di aiuto"*.
  - *Sto bene* → evento Tier A fortissimo, headline verde, audit.
  - *Aiuto* → **evento rosso esplicito** (una delle poche fonti legittime di
    rosso), alert immediato a tutti i caregiver autorizzati.

## Gradino 5 — Canale audio

### Audio in uscita (la voce del caregiver dall'altoparlante del subject)

Nessun ostacolo: FCM → l'app riproduce su stream ALARM. Messaggio registrato, TTS,
o canale WebRTC live. Nessuna accettazione richiesta. Tecnicamente il più semplice
dei cinque.

### Audio in ingresso (ascoltare l'ambiente)

Tecnicamente possibile (`RECORD_AUDIO` + foreground service tipo microfono), ma
Android **impone** notifica persistente e indicatore verde: non si può fare di
nascosto, e non si deve provare.

**Design: canale che si annuncia.** Il telefono dice ad alta voce *"Marco ha
aperto un canale audio"*, poi apre il microfono. Nessuna accettazione necessaria,
trasparenza totale. Per lo scenario "è caduta e non può premere niente" funziona
identico a un ascolto silenzioso, senza costruire uno strumento di sorveglianza
occulta — e sul piano legale (EU) tiene dalla parte giusta.

> Il concetto di "accettare la chiamata" del subject **non serve**: il canale si
> apre da solo dopo l'annuncio. Se in futuro si vuole una conferma esplicita, è un
> gradino 5-bis opzionale.

### Sul watch

Anche se il Watch 6 avesse altoparlante/microfono (da verificare), instradare
l'audio dell'app sul watch è fragile (dipende dal routing BT). Si lascia perdere:
il telefono è con la persona.

## Requisito trasversale: consenso sulla scala, non sulle singole azioni

Ai gradini 3–5 il collector è a tutti gli effetti un **telecomando sul telefono di
un'altra persona**. Serve che il subject:

1. veda e approvi **la scala** in fase di setup (non le singole azioni);
2. abbia nella propria app uno **storico consultabile** di chi ha attivato cosa e
   quando (alimentato da `audit_log` + `escalation_action`).

È ciò che rende il sistema difendibile. Dettagli in
[`07-authorization-privacy.md`](07-authorization-privacy.md).

## Mappa gradino → dati

| Gradino | Tabelle coinvolte |
|---------|-------------------|
| 1 | `liveness_snapshot` |
| 2 | `checkin_request`, `activity_event`, `location_fix` |
| 3–5 | `escalation_action`, `confirmation_response`, `audit_log` |

Definizioni in [`05-data-model.md`](05-data-model.md); endpoint in
[`06-api.md`](06-api.md).
