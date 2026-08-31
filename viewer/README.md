# Accanto — viewer

Web app per i caregiver. Next.js 15 (App Router) + TypeScript strict.

Progetto: [`../README.md`](../README.md) · design:
[`../docs/10-viewer-web.md`](../docs/10-viewer-web.md) · mockup di partenza:
[`../design/accanto-mobile.dc.html`](../design/accanto-mobile.dc.html).

## Avvio

```bash
npm install
cp .env.example .env.local
npm run dev
```

Serve il backend attivo su `http://localhost:8000`.

## Verifica

```bash
npm test        # 31 test sulla logica pura
npm run typecheck
npm run build
```

## Perché web e non un'app

Per lo scopo «chiunque io autorizzi», un **link** è più semplice da distribuire e
soprattutto da **revocare** di un APK. Nessuno store, nessun aggiornamento
forzato, i caregiver possono stare su Android, iPhone o desktop.

## Sicurezza della sessione

Il token del backend vive in un cookie **httpOnly**, letto solo lato server:

- non è in `localStorage`, non è in una variabile JS, non è nell'URL;
- tutte le chiamate all'API partono dal server Next.js;
- il browser non conosce nemmeno l'indirizzo del backend.

Da qui la scelta di **SSE invece del WebSocket** per il realtime: `new
WebSocket(url?token=…)` avrebbe richiesto di consegnare a JavaScript una
credenziale per dati sanitari e di posizione, che sarebbe finita anche nella
cronologia del browser e nei log dei proxy. Lo stream è invece proxato da
[`app/api/stream/route.ts`](app/api/stream/route.ts), che aggiunge
l'`Authorization` lato server.

Altre misure: `X-Frame-Options: DENY`, `nosniff`, `Referrer-Policy: no-referrer`,
`Permissions-Policy` che nega geolocalizzazione, microfono e camera; CSRF coperto
da SameSite=Lax più la validazione dell'`Origin` che Next fa sulle Server Action.

> In produzione servono HTTPS e `ACCANTO_SECURE_COOKIES=1`. Vedi
> [`../docs/13-deployment.md`](../docs/13-deployment.md).

## Dal mockup al codice

I token in [`app/globals.css`](app/globals.css) sono presi dal file di Claude
Design. Tre scelte si sono rese necessarie perché il mockup mostrava **solo il
percorso felice**:

1. **Il colore è diventato semantico.** Nel mockup tutti i tile dei tier erano
   verdi, incluso quello dei segni vitali — corretto per caso, perché
   raffigurava l'istante in cui tutti gli orologi sono freschi. Preso alla
   lettera, un sistema silenzioso sarebbe rimasto verde e rassicurante mentre la
   headline diceva il contrario. Ora ogni tile è verde solo finché il suo
   orologio è fresco.
2. **Il contatto di sistema non è mai verde.** Prova che la pipeline funziona,
   non che la persona stia bene.
3. **Etichette neutre rispetto al genere.** Il mockup diceva «Maurizio · Attiva»;
   il nome è configurabile, quindi gli stati sono costruiti su sintagmi nominali
   («In attività», «In movimento») che funzionano per chiunque.

Ambra `#A8763A`, grigio `#9B9686` e rosso `#A4503F` sono derivati per restare
nella palette calda del design. Il rosso compare di rado: non deve urlare per
essere preso sul serio.

## Struttura

```
app/
  login/            accesso (Server Action → cookie httpOnly)
  s/[subjectId]/    presenza · mappa · contatto
  api/              proxy server-side: stream SSE, check-in, escalation
components/         PresenceView, EscalationLadder, LocationMap, BottomNav
lib/
  presence.ts       stato → etichetta e tono          (testato)
  time.ts           tempo relativo in italiano        (testato)
  api.ts            client server-side del backend
  session.ts        cookie di sessione
```

`lib/presence.ts` e `lib/time.ts` sono puri e senza I/O: la logica che decide
cosa legge un caregiver è verificabile in millisecondi.

## Invarianti protette da test

- Le etichette di stato **non contengono aggettivi che concordano** con la persona.
- Un tier è verde **solo se il suo orologio è fresco**.
- Il contatto di sistema **non è mai verde**.
- Nessuno stato della headline produce **rosso** (è riservato agli alert).
- L'assenza di dati è **grigia e spiegata**, mai un allarme.
- La stima «probabilmente in carica» resta **una stima** nel testo mostrato.
- Un orologio del telefono avanti non produce mai «fra N minuti».

## Cosa manca

Storico e grafici, gestione dei grant dall'interfaccia, Web Push per gli alert,
schermata di audit per il subject, refresh automatico della sessione (il backend
espone `/v1/auth/refresh`, il viewer non lo usa ancora).
