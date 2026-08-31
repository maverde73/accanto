# 00 — Overview

## Visione

Dare a chi si prende cura di una persona cara una risposta rapida, affidabile e
rispettosa alla domanda *"come sta, adesso?"*, senza trasformare quella persona in
un soggetto sorvegliato.

Il sistema è costruito su una tensione che ne guida ogni scelta:

> **Massima informazione per il caregiver, minima invasività per la persona.**

Ogni funzionalità è collocata su una scala che va da *"leggo passivamente ciò che
già esiste"* a *"interrompo attivamente la persona per avere certezza"*. Il
sistema non decide da solo dove fermarsi: espone la scala e lascia che sia il
caregiver a salirla, un gradino alla volta, solo finché non ha la risposta.

## Scenario primario

La persona monitorata è un familiare adulto e autonomo (es. un genitore anziano)
che:

- **indossa sempre** il Redmi Watch 6, togliendolo solo per la ricarica;
- **porta sempre con sé** il proprio smartphone (Samsung Galaxy S24) e non lo
  lascia a casa;
- vive in modo indipendente, ma il caregiver vuole poter verificare rapidamente il
  suo stato quando non risponde.

Da queste due assunzioni derivano due semplificazioni importanti:

1. **Watch = sempre indossato, tranne in carica.** Non serve un sensore
   "wear detection": l'assenza prolungata di dati cardiaci a persona ferma viene
   interpretata come "probabilmente in carica".
2. **Telefono = sempre con la persona.** La posizione del telefono è una buona
   proxy della posizione della persona (con i limiti di precisione del GPS).

> ⚠️ Queste assunzioni sono comode ma non sono garanzie. La UI non deve mai
> presentare un'inferenza come un fatto: "probabilmente in carica", non "in
> carica". Vedi [`03-liveness-model.md`](03-liveness-model.md).

## Scenario d'uso concreto

1. Il caregiver chiama, la persona non risponde.
2. Apre la web app Accanto e guarda lo **stato di presenza**: nella maggioranza
   dei casi qui la domanda è già risolta ("ha sbloccato il telefono 4 minuti fa",
   "sta camminando"). Fine.
3. Se lo stato non basta, preme **"Come sta?"** → check-in on-demand: il sistema
   forza un aggiornamento e restituisce un bundle fresco (battito, movimento
   recente, posizione, batterie).
4. Se serve un contatto, sale la **scala di escalation**: fa vibrare il polso,
   manda una richiesta di conferma *"sto bene?"*, fino ad aprire un canale audio.
5. Ogni azione è registrata in un **audit log** che la persona monitorata può
   consultare.

## Obiettivi

- **O1.** Rispondere a *"come sta ora?"* in secondi nel caso comune, in pochi
  minuti nel caso peggiore.
- **O2.** Distinguere in modo affidabile tre situazioni che una lettura ingenua
  confonde: *persona attiva*, *persona ferma ma presente*, *dati assenti*.
- **O3.** Non generare mai falsi allarmi da guasti della pipeline (watch in
  carica, telefono scarico, app uccisa dall'OS).
- **O4.** Fornire una via di **contatto attivo** graduata, dalla più discreta alla
  più intrusiva.
- **O5.** Mappa di posizione in tempo reale, con zone note (geofence).
- **O6.** Autorizzazioni esplicite, granulari, revocabili; tracciabilità completa
  degli accessi.

## Non-obiettivi (fase 1)

- **NG1.** Alert cardiaci in tempo reale. Impossibile con questo hardware senza
  reverse engineering del BLE; rimandato a un'eventuale fase 2 e comunque incerto.
- **NG2.** Rilevamento cadute lato watch. L'accelerometro del watch non è
  accessibile.
- **NG3.** Dispositivo medico. Accanto **non** è un dispositivo medico, non
  diagnostica, non sostituisce un sistema di teleassistenza certificato o una
  chiamata ai servizi di emergenza.
- **NG4.** Multi-soggetto su larga scala. L'architettura lo permette, ma la fase 1
  è tarata su **una** persona monitorata e pochi caregiver.
- **NG5.** App iOS per il collector. Il collector richiede Android. I *viewer*
  invece sono web e funzionano ovunque.

## Attori

| Attore | Descrizione | Interfaccia |
|--------|-------------|-------------|
| **Subject** (persona monitorata) | Chi indossa il watch e porta il telefono | App collector sul proprio telefono (setup + audit + consenso) |
| **Caregiver** | Chi autorizza sé stesso a monitorare, con permessi concessi dal subject | Web app viewer |
| **Owner / admin** | Chi amministra i grant (spesso coincide col subject o con un caregiver di fiducia) | Web app |
| **Collector** | L'app Android sul telefono del subject; agisce come *device*, non come persona | — (servizio) |

## Metriche di successo

- Tempo di risposta di un check-in on-demand: **< 15 s** per i segnali di telefono,
  **< 2 min** per il battito fresco (P90).
- Falsi allarmi da guasto pipeline presentati come "rosso": **0**.
- Continuità del collector: l'app resta viva e autorizzata **≥ 30 giorni** senza
  intervento manuale (dopo il setup iniziale).
- Un caregiver non tecnico capisce lo stato di presenza **senza spiegazioni**.

## Glossario rapido

I termini ricorrenti (tier, headline, grant, check-in, escalation, snapshot) sono
definiti in [`12-glossary.md`](12-glossary.md).
