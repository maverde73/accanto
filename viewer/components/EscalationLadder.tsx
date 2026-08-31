"use client";

import { useState } from "react";

/** The ladder, presented as what it is.
 *
 * Each rung states plainly what the subject will experience, because the
 * caregiver is choosing how much to intrude, not just which button to press.
 * Rungs the grant does not cover are shown disabled rather than hidden: seeing
 * that a louder option exists, and that it was not granted, is part of
 * understanding the arrangement.
 */

interface Rung {
  rung: number;
  actionType: string;
  title: string;
  effect: string;
  scope: string;
  tone: "green" | "amber" | "red";
  /** Declared but not yet built. Offering a button that always fails would
   *  tell the caregiver something happened when nothing did. */
  unavailable?: boolean;
}

const RUNGS: Rung[] = [
  {
    rung: 3,
    actionType: "vibrate",
    // Named for what it does, not what it was hoped to do. It was called "make
    // the wrist buzz", relying on Mi Fitness mirroring phone notifications to
    // the watch -- which does not happen on the tested phone. A rung that
    // promises the wrist and reaches only the phone is the kind of small lie
    // that costs a caregiver their trust in everything else here.
    title: "Avvisa sul telefono",
    effect:
      "Una notifica discreta con vibrazione, senza suoni. Può rispondere «sto bene» " +
      "con un tocco, senza aprire nulla. Arriva anche al polso solo se l'orologio è " +
      "impostato per ripetere le notifiche del telefono.",
    scope: "escalation:notify",
    tone: "green",
  },
  {
    rung: 4,
    actionType: "confirm_prompt",
    title: "Chiedi conferma «stai bene?»",
    effect:
      "Schermata a tutto schermo e suono che supera il silenzioso. Se tocca «sto bene», hai una certezza, non una deduzione.",
    scope: "escalation:alarm",
    tone: "amber",
  },
  {
    rung: 5,
    actionType: "audio_channel",
    title: "Apri un canale audio",
    effect:
      "Il telefono annuncia ad alta voce chi sta aprendo il canale, poi attiva il microfono. Nessun ascolto silenzioso.",
    scope: "escalation:audio",
    tone: "red",
    unavailable: true,
  },
];

const CONFIRMATION_TIMEOUT_MS = 45_000;
const POLL_INTERVAL_MS = 3_000;

/** Polls until the phone confirms the rung was carried out, or we give up. */
async function waitForExecution(subjectId: string, escalationId: string): Promise<boolean> {
  const deadline = Date.now() + CONFIRMATION_TIMEOUT_MS;

  while (Date.now() < deadline) {
    await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS));

    const response = await fetch(`/api/escalations?subject=${encodeURIComponent(subjectId)}`);
    if (!response.ok) continue;

    const list = (await response.json()) as Array<{ id: string; status: string }>;
    const mine = list.find((item) => item.id === escalationId);
    if (mine && mine.status !== "sent") return mine.status === "executed";
  }
  return false;
}

export function EscalationLadder({
  subjectId,
  scopes,
}: {
  subjectId: string;
  scopes: string[];
}) {
  const [busy, setBusy] = useState<string | null>(null);
  const [result, setResult] = useState<{ ok: boolean; text: string } | null>(null);

  async function invoke(rung: Rung) {
    setBusy(rung.actionType);
    setResult(null);

    const response = await fetch(`/api/escalate?subject=${encodeURIComponent(subjectId)}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action_type: rung.actionType, params: {} }),
    });

    if (!response.ok) {
      setBusy(null);
      setResult({ ok: false, text: "Non hai il permesso per questa azione." });
      return;
    }

    const created = (await response.json()) as { id: string };
    setResult({ ok: true, text: "Richiesta inoltrata. Attendo conferma dal telefono…" });

    // Accepted by the server is not the same as carried out on the phone, and
    // the difference is exactly what the caregiver is asking about. Reporting
    // "sent" and stopping there would leave them believing something happened.
    const executed = await waitForExecution(subjectId, created.id);
    setBusy(null);
    setResult(
      executed
        ? { ok: true, text: `Eseguito sul telefono: ${rung.title.toLowerCase()}.` }
        : {
            ok: false,
            text:
              "Il telefono non ha confermato. La richiesta resta in attesa e verrà eseguita " +
              "appena il telefono tornerà raggiungibile.",
          },
    );
  }

  return (
    <>
      <p className="muted" style={{ margin: 0 }}>
        Sali un gradino alla volta, solo finché non ottieni risposta. Ogni azione resta
        registrata e la persona può consultarla.
      </p>

      {RUNGS.map((rung) => {
        const allowed = scopes.includes(rung.scope);
        return (
          <div key={rung.actionType} className={`card tone-${rung.tone}`} style={{ padding: 16 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <span className="dot" />
              <strong style={{ fontSize: 15 }}>{rung.title}</strong>
              <span style={{ marginLeft: "auto", fontSize: 12, color: "var(--ink-faint)" }}>
                gradino {rung.rung}
              </span>
            </div>
            <p
              style={{
                fontSize: 13.5,
                color: "var(--ink-secondary)",
                lineHeight: 1.5,
                margin: "8px 0 12px",
              }}
            >
              {rung.effect}
            </p>
            <button
              className="btn btn-secondary"
              style={{ height: 42 }}
              disabled={!allowed || rung.unavailable || busy !== null}
              onClick={() => invoke(rung)}
            >
              {rung.unavailable
                ? "Non ancora disponibile"
                : !allowed
                  ? "Non autorizzato"
                  : busy === rung.actionType
                    ? "Invio…"
                    : "Esegui"}
            </button>
          </div>
        );
      })}

      {result ? (
        <div className={`banner ${result.ok ? "tone-green" : "tone-amber"}`}>{result.text}</div>
      ) : null}
    </>
  );
}
