# 12 — Glossario

Termini ricorrenti nella documentazione di Accanto.

| Termine | Definizione |
|---------|-------------|
| **Subject** | La persona monitorata: chi indossa il watch e porta il telefono. |
| **Caregiver** | Chi è autorizzato a monitorare il subject, con permessi (scope) concessi tramite un grant. |
| **Owner** | Chi amministra i grant di un subject (spesso il subject stesso o un caregiver di fiducia). |
| **Collector** | L'app Android sul telefono del subject; agisce come *device*, non come persona. |
| **Viewer** | La web app usata dai caregiver. |
| **Tier** | Categoria di un segnale in base a *cosa dimostra*: A = interazione (cosciente), B = movimento, C = segni vitali (vivo), D = contatto di sistema (né persona né attività). |
| **Headline** | Lo stato di presenza sintetico mostrato al caregiver (Attiva / In movimento / Ferma / Silenziosa / Nessun dato), con colore. |
| **Liveness snapshot** | La riga derivata (una per subject) che riassume i quattro orologi e la headline; riscritta a ogni ingest. |
| **Orologio (clock)** | Uno dei quattro timestamp per-tier: ultimo evento di interazione / movimento / vitale / contatto. |
| **Check-in** | Richiesta on-demand del caregiver ("come sta?") che forza un aggiornamento (gradino 2 della scala). |
| **Escalation ladder** | La scala di 5 gradini di contatto, dal passivo (lettura) all'attivo (audio). |
| **Gradino (rung)** | Un livello della scala di escalation (2 = check-in, 3 = vibrazione, 4 = allarme+conferma, 5 = audio). |
| **Grant** | Autorizzazione di un subject verso un caregiver: scope + scadenza + stato, revocabile. |
| **Scope** | Una specifica capacità concessa da un grant (es. `liveness`, `location:precise`, `escalation:alarm`). |
| **`occurred_at`** | Quando un dato è *accaduto*, secondo l'orologio del device. È ciò che la UI mostra sempre. |
| **`received_at`** | Quando un dato è *arrivato* al backend. Serve solo a misurare la salute della pipeline. |
| **`dedup_key`** | Chiave deterministica che rende idempotente l'ingest (il collector ritrasmette dopo ogni disconnessione). |
| **Idempotenza** | Proprietà per cui ricevere due volte lo stesso evento non altera il risultato (upsert su `dedup_key`). |
| **Pipeline (salute della)** | Metrica di funzionamento del flusso dati (lag `received_at − occurred_at`, ultimo contatto, permessi). Distinta dallo stato della persona. |
| **`watch_likely_charging`** | Inferenza (non certezza) che il watch sia in carica: gap HR prolungato + passi fermi. |
| **Geofence** | Zona geografica nominata (es. "Casa") usata per stati e alert ("è uscito"). |
| **Foreground service** | Servizio Android persistente con notifica visibile; è ciò che tiene vivo il collector contro Doze e i kill di One UI. |
| **Health Connect** | Hub dati sanitari di Android; Mi Fitness ci scrive HR/passi/sonno e il collector li legge. |
| **Mi Fitness** | App Xiaomi che gestisce il watch via BLE; per noi è il gateway (sync, mirroring notifiche). |
| **Vela** | Il sistema operativo del watch (RTOS Xiaomi, non Wear OS): rende il watch non programmabile. |
| **Mirroring notifiche** | Funzione di Mi Fitness che replica le notifiche del telefono sul watch (usata per far vibrare il polso al gradino 3). |
| **Stream ALARM** | Canale audio Android delle sveglie: ignora silenzioso/vibrazione/DND; usato per il ring del gradino 4. |
| **Doze** | Modalità di risparmio energetico di Android che sospende le app in background; le push FCM high-priority ne sono esenti. |
| **Permission Dashboard** | Schermata del collector che verifica e ripara i permessi (speciali e non), garantendo la longevità del sistema. |
| **Risposta progressiva** | Pattern del check-in: prima i segnali del telefono (secondi), poi il battito fresco (decine di secondi). |
