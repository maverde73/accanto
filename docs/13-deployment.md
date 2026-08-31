# 13 — Deployment via Cloudflare Tunnel

## Perché non su Cloudflare Workers

Valutato e scartato. I Workers girano su isolate V8 (JavaScript/WASM):

- i **Python Workers** esistono ma sono basati su Pyodide; `asyncpg` e
  `argon2-cffi` sono estensioni C native e non ci girano;
- **SSE a lunga durata** mal si concilia con i limiti di CPU/durata dei Worker;
- Cloudflare **non ospita PostgreSQL** (D1 è SQLite, Hyperdrive è solo un pooler
  verso un Postgres esterno).

Riscrivere il backend per adattarlo significherebbe cambiare linguaggio,
database e modello di concorrenza. Non vale il beneficio.

## L'architettura scelta

Backend e viewer girano sulla macchina di casa; **`cloudflared`** li espone.

```
        Internet
            │  HTTPS (certificato Cloudflare)
            ▼
    ┌───────────────────┐
    │  Cloudflare edge  │
    └─────────┬─────────┘
              │  tunnel cifrato in uscita — nessuna porta aperta in ingresso
              ▼
    ┌─────────────────────────────────────────┐
    │  macchina di casa                        │
    │                                          │
    │  cloudflared                             │
    │    ├── accanto.maurizioverde.info        │
    │    │     └──► localhost:3000  (viewer)   │
    │    └── accanto-api.maurizioverde.info    │
    │          └──► localhost:8000  (backend)  │
    │                                          │
    │  postgres  localhost:5432 (mai esposto)  │
    └─────────────────────────────────────────┘
```

### Perché `accanto-api` e non `api.accanto`

Il certificato Universal SSL di Cloudflare copre `dominio.tld` e `*.dominio.tld`:
**un solo livello di sottodominio**. `api.accanto.maurizioverde.info` ne ha due,
e l'handshake TLS fallisce con `handshake failure` — sintomo opaco, perché il
DNS risolve correttamente e il tunnel è connesso.

Coprire due livelli richiede Advanced Certificate Manager, a pagamento. Un nome
piatto lo evita del tutto.

> Verificato sul campo: `accanto.maurizioverde.info` (un livello) rispondeva 200
> mentre `api.accanto.maurizioverde.info` (due) falliva, con lo stesso tunnel e
> gli stessi record.

### Perché due hostname e non uno

Il viewer serve i **caregiver** via browser; il backend serve anche il
**collector Android**, che non passa da Next.js. Servono quindi entrambi
raggiungibili, ma restano due superfici distinte:

- `accanto.maurizioverde.info` → **viewer**. Nessuno dei suoi utenti conosce
  l'indirizzo dell'API, e il token di sessione non lascia mai il server.
- `accanto-api.maurizioverde.info` → **backend**, per il solo collector.

Un routing per path su un unico hostname funzionerebbe, ma renderebbe l'API
raggiungibile dal browser dei caregiver senza alcun motivo: due nomi tengono le
superfici separate a costo zero.

**PostgreSQL non compare nell'ingress**: resta su localhost, raggiungibile solo
dal backend.

## Configurazione

### 1. Tunnel

```bash
cloudflared tunnel login
cloudflared tunnel create accanto
cloudflared tunnel route dns accanto accanto.maurizioverde.info
cloudflared tunnel route dns accanto accanto-api.maurizioverde.info
```

### 2. `~/.cloudflared/config.yml`

```yaml
tunnel: accanto
credentials-file: /home/mverde/.cloudflared/<TUNNEL_ID>.json

ingress:
  - hostname: accanto.maurizioverde.info
    service: http://localhost:3000

  - hostname: accanto-api.maurizioverde.info
    service: http://localhost:8000
    originRequest:
      # Lo stream SSE del realtime deve restare aperto e non essere bufferizzato.
      connectTimeout: 30s
      noHappyEyeballs: true

  # Qualunque altro host che arrivi al tunnel non deve trovare nulla.
  - service: http_status:404
```

### 3. Avvio persistente

```bash
sudo cloudflared service install
sudo systemctl enable --now cloudflared
```

## Variabili d'ambiente in produzione

### Backend (`backend/.env`)

```bash
ACCANTO_ENVIRONMENT=production
ACCANTO_DEBUG=false
ACCANTO_DATABASE_URL=postgresql+asyncpg://accanto:<password>@localhost:5432/accanto
ACCANTO_JWT_SECRET=<48+ caratteri casuali>
# Vuoto di proposito: nessun browser chiama direttamente il backend, e il
# collector è nativo (CORS non si applica). Una wildcard verrebbe comunque
# rifiutata all'avvio.
ACCANTO_CORS_ORIGINS=
```

Genera il secret con:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

L'avvio **fallisce di proposito** se `ACCANTO_JWT_SECRET` è ancora il valore di
sviluppo: meglio un servizio che non parte di uno che serve dati sanitari
firmandoli con una chiave pubblicata su GitHub.

### Viewer (`viewer/.env.local`)

```bash
# Interno: il viewer raggiunge il backend su localhost, non attraverso il tunnel.
ACCANTO_API_URL=http://localhost:8000
# Ora che il traffico è HTTPS, il cookie di sessione porta il flag Secure.
ACCANTO_SECURE_COOKIES=1
```

### Collector Android

```
BASE_URL = https://accanto-api.maurizioverde.info
```

## SSE attraverso Cloudflare

Lo streaming funziona, con due accortezze già implementate nel backend:

- **keepalive ogni 25 s** (`app/api/sse.py`), che tiene la connessione sotto le
  soglie di inattività dei proxy intermedi;
- header `Cache-Control: no-cache, no-transform` e `X-Accel-Buffering: no`, che
  impediscono la bufferizzazione della risposta.

Se in futuro lo stream dovesse chiudersi a intervalli regolari, il sospetto
principale è un timeout di inattività: la cura è abbassare il keepalive, non
allungare i timeout.

## Trappole incontrate davvero

**Il certificato dell'account `cloudflared` vale per una zona sola.**
`cloudflared tunnel route dns` con un hostname di un'altra zona non fallisce:
crea silenziosamente il record **dentro la zona autorizzata**, appendendo il
suffisso (`accanto.tuodominio.it` diventa
`accanto.tuodominio.it.zona-del-cert.net`). Se i record non compaiono dove te li
aspetti, è questo. Rimedio: crearli a mano dal dashboard come CNAME verso
`<tunnel-id>.cfargotunnel.com`, **proxied**.

**La rete di casa può non risolvere gli hostname dei tunnel.** Su questa rete i
domini normali risolvono e quelli dei tunnel restituiscono NXDOMAIN, sia via
`1.1.1.1` sia via `8.8.8.8` in chiaro — mentre gli stessi provider via DoH
rispondono correttamente. Il DNS in chiaro viene intercettato dal router. Non è
un problema del tunnel: da fuori casa funziona. Rimedio lato client: DNS over
HTTPS nel browser.

**Errore 1033 durante un riavvio** è normale: è Cloudflare che non trova il
tunnel per i secondi in cui `cloudflared` non è in esecuzione.

## Il compromesso, detto chiaramente

Ospitare in casa un sistema di caregiving significa che **la sua disponibilità
dipende dalla tua macchina e dalla tua linea**. Se la macchina si spegne o
Internet cade:

- il **collector continua ad accumulare** in locale e ritrasmette dopo
  (l'ingest è idempotente, i dati non si perdono);
- ma il caregiver **non vede nulla** e **nessun alert parte** finché il servizio
  non torna.

Per un uso familiare è un compromesso ragionevole. Va però sostenuto con:

- **UPS** sulla macchina e sul router;
- avvio automatico di Postgres, backend, viewer e `cloudflared` al boot;
- un **monitor esterno** che avvisi *te* se `accanto.maurizioverde.info` non
  risponde — perché altrimenti l'unico segnale di un guasto sarebbe il silenzio,
  che è esattamente ciò che il sistema dovrebbe distinguere da una persona che
  sta bene.

L'ultimo punto non è un dettaglio operativo: un sistema che non sa dire "sono
rotto" ricade nel modo di fallire che l'intero design cerca di evitare.

## Backup

I dati sono sanitari e di localizzazione: il backup va **cifrato**.

```bash
docker exec accanto-pg pg_dump -U accanto accanto \
  | age -r <chiave-pubblica> > accanto-$(date +%F).sql.age
```

Retention coerente con [`07-authorization-privacy.md`](07-authorization-privacy.md):
i backup non devono sopravvivere alla cancellazione richiesta da un subject.
