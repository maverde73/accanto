# Accanto — backend

FastAPI + PostgreSQL. Verità unica del sistema: ingest, calcolo della presenza,
autorizzazioni, canale comandi.

Progetto complessivo: [`../README.md`](../README.md) ·
design: [`../docs/09-backend.md`](../docs/09-backend.md).

## Avvio rapido

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
cp .env.example .env
.venv/bin/uvicorn app.main:app --reload
```

API su `http://localhost:8000`, documentazione interattiva su `/docs`.

## Test

```bash
.venv/bin/python -m pytest -q
```

I test del dominio (`test_liveness.py`, `test_dedup.py`) **non richiedono un
database**: `app/domain/` è stdlib puro, senza I/O. È una scelta deliberata — la
logica che decide cosa vede un caregiver dev'essere verificabile in millisecondi.

I test marcati `@pytest.mark.integration` richiedono un PostgreSQL attivo:

```bash
.venv/bin/python -m pytest -m "not integration"   # solo unit
```

## Struttura

```
app/
  domain/        logica pura: tier, fusione presenza, chiavi di dedup (no I/O)
  models/        tabelle SQLAlchemy
  schemas/       contratti Pydantic in ingresso/uscita
  repositories/  accesso dati
  services/      orchestrazione (LivenessService, IngestService)
  api/           router FastAPI e dipendenze
  core/          config, sessione DB, sicurezza
```

La dipendenza va **sempre** verso l'interno: `api → services → repositories →
models`, e `domain` non dipende da nulla. Se un giorno cambia il framework o il
database, il dominio non si tocca.

## Invarianti protette da test di regressione

Sono le regole che decidono se il prodotto è affidabile, non dettagli:

1. **La fusione non produce mai il rosso.** Nessuna combinazione di dati mancanti
   o vecchi può generare un allarme. Il rosso nasce solo dalla presenza positiva
   di un problema. (`test_fusion_never_produces_red`)
2. **Il silenzio totale è grigio, mai ambra o verde.** La causa più comune è un
   guasto della pipeline; colorarlo come allarme insegna a ignorare gli allarmi.
3. **La headline porta l'ora dell'evento, non quella del sync.** Un batch di dati
   vecchi che arriva ora non è attività attuale.
4. **Il tier è derivato dal server**, mai preso dal payload: un collector
   manomesso non deve poter promuovere un segnale debole a prova di coscienza.
   (`test_client_cannot_choose_its_own_tier`)

## Stato

Fase 1 in corso. Implementato: dominio della presenza, modelli (9 tabelle),
ingest idempotente, snapshot, autenticazione device.

Ancora da fare: migrazioni Alembic, autorizzazione per scope sui grant, check-in
on-demand e canale comandi FCM, realtime WebSocket, alert engine.

## Note di implementazione

- **`access_grant`, non `grant`**: `GRANT` è una parola riservata SQL.
- **Token device**: hash SHA-256 (stringhe casuali ad alta entropia, non
  password). Argon2 resta per le password utente.
- **Bucketing delle dedup key**: finestre fisse allineate all'epoch, non
  scorrevoli — la chiave dev'essere calcolabile da un evento isolato. Il debounce
  vero è responsabilità del collector.
