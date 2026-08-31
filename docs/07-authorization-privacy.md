# 07 — Autorizzazioni e privacy

Non è un capitolo "di conformità" da mettere in fondo: il modello di autorizzazione
**condiziona lo schema del DB** ([`05`](05-data-model.md)) e va deciso all'inizio
perché è costoso cambiarlo dopo.

## Principio guida

> Non "accesso sì/no", ma: **questo caregiver, queste metriche, questa
> granularità, fino a questa data — revocabile in ogni momento, e tracciato.**

## Il modello dei grant

Un `grant` collega un `subject` a un `app_user` (caregiver) con:

- **scopes** — quali metriche e con quale dettaglio (elenco in [`05`](05-data-model.md));
- **expires_at** — scadenza opzionale (un grant "per il weekend" scade da solo);
- **status** — `active` / `revoked` / `expired`;
- **granted_by** — chi l'ha concesso (per l'audit).

### Esempi di grant reali

| Situazione | Scopes | Scadenza |
|-----------|--------|----------|
| Figlio, caregiver primario | `liveness, vitals, location:precise, history, escalation:*` | nessuna |
| Vicino di casa di fiducia | `liveness, location:coarse, escalation:notify` | nessuna |
| Amico durante una gita | `liveness, location:precise` | fine giornata |
| Medico curante | `vitals, history` | 30 giorni, rinnovabile |

La granularità `location:coarse` vs `location:precise` e la scomposizione
dell'escalation (`notify`/`alarm`/`audio`) esistono proprio per rendere esprimibili
questi casi. *"Può sapere se sta bene ma non dove si trova"* = `liveness` senza
`location:*`.

## Applicazione degli scope (dove, come)

- **Lato server, sempre.** Ogni endpoint verifica scope + scadenza + stato prima di
  rispondere. Il filtro non è mai lato client.
- **Riduzione di risoluzione al server.** Un caregiver `location:coarse` riceve
  coordinate arrotondate o il nome della geofence; il dato preciso **non lascia il
  backend**. Non si manda il preciso "nascondendolo" nella UI.
- **Realtime coerente.** Il canale WS/SSE applica gli stessi scope dei REST.
- **Revoca immediata.** `DELETE /grants/{id}` invalida sessioni e canali realtime
  del grantee per quel subject entro pochi secondi.

## Consenso del subject

Il consenso qui è **strutturalmente garantito** dal design: la persona monitorata
deve installare e configurare l'app sul proprio telefono. Nessuno può monitorarla
senza il suo dispositivo e la sua azione. Ma "strutturale" non basta: serve
consenso **informato** e **consultabile**.

### Consenso sulla scala di escalation, non sulle singole azioni

Ai gradini 3–5 il collector è un telecomando sul telefono del subject. Il subject
deve, in fase di setup:

1. **vedere e approvare la scala** (cosa può fare un caregiver: far vibrare,
   suonare l'allarme, aprire l'audio) — non le singole invocazioni;
2. poter **decidere quali gradini abilitare** (es. abilitare vibrazione e conferma,
   ma non il canale audio) → si traduce negli scope concessi;
3. avere sul proprio telefono uno **storico consultabile** (`audit_log` +
   `escalation_action`) di chi ha attivato cosa e quando.

### Trasparenza come feature

- Le azioni di escalation sono **visibili** (notifica, allarme, annuncio audio):
  niente comportamenti occulti.
- L'**audio in ingresso si annuncia sempre** (imposto da Android e abbracciato dal
  design, vedi [`04`](04-escalation-ladder.md)).
- Il subject può **revocare** qualunque grant dal proprio telefono (non solo
  l'owner).

## Audit log

Ogni azione sensibile è registrata in `audit_log`:

- **letture sensibili**: visualizzazione posizione precisa, accesso allo storico
  vitali;
- **azioni**: check-in, ogni gradino di escalation, apertura canale audio;
- **amministrazione**: creazione/modifica/revoca di grant.

Consultabile sia dall'owner sia dal **subject stesso**. È il registro che rende il
sistema difendibile se un domani qualcuno lo mette in discussione.

## Inquadramento legale (GDPR / EU)

> Questa sezione è un orientamento, non un parere legale. Per un uso che esca dalla
> stretta cerchia familiare, far verificare a un professionista.

- **Categoria dei dati.** Battito cardiaco = dato sanitario (art. 9 GDPR).
  Posizione = dato personale, e la localizzazione continua di una persona è
  particolarmente invasiva. Entrambi richiedono tutele rafforzate.
- **Esenzione domestica (art. 2(2)(c)).** Finché il trattamento è *strettamente
  personale o domestico* (io monitoro un mio familiare, dati non condivisi con
  terzi), si è fuori dall'ambito pieno del GDPR. **Aprendo a terzi** (altri
  caregiver, un medico, un servizio) l'esenzione **decade** e servono base
  giuridica (il consenso esplicito ex art. 9(2)(a)), informativa, minimizzazione,
  ecc.
- **Base giuridica.** Il **consenso esplicito** del subject è la base naturale.
  Deve essere libero, informato, specifico e **revocabile** — ed è esattamente ciò
  che il modello dei grant + revoca implementa.
- **Minimizzazione.** Concedere solo gli scope necessari; preferire
  `location:coarse` dove il preciso non serve; retention limitata (vedi sotto).
- **Non è un dispositivo medico.** Non diagnostica, non allerta i soccorsi
  automaticamente, non sostituisce la teleassistenza certificata. Va scritto
  nell'app.

## Retention e cancellazione

| Dato | Retention default | Note |
|------|-------------------|------|
| `activity_event`, `location_fix` | 90 giorni | poi aggregati in `activity_baseline` e cancellati in dettaglio |
| `liveness_snapshot` | corrente | solo lo stato attuale |
| `checkin_request`, `escalation_action`, `audit_log` | 1 anno | tracciabilità |
| `alert_event` | 1 anno | |

- **Diritto alla cancellazione:** `DELETE /subjects/{id}` cancella a cascata tutti
  i dati del subject (le FK sono `on delete cascade`).
- **Export:** un endpoint owner per esportare tutti i dati di un subject (portabilità).

## Sicurezza tecnica (rimando)

Cifratura in transito (HTTPS ovunque), a riposo (disco cifrato + cifratura a
livello colonna per i vitali se richiesto), token per-device revocabili, secret
solo in env, CORS con origini esplicite in produzione. Dettagli operativi in
[`09-backend.md`](09-backend.md).
