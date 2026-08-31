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
}

const RUNGS: Rung[] = [
  {
    rung: 3,
    actionType: "vibrate",
    title: "Fai vibrare il polso",
    effect: "Una notifica discreta sul telefono, che l'orologio ripete al polso.",
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
  },
];

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
    setBusy(null);
    setResult(
      response.ok
        ? { ok: true, text: `Inviato: ${rung.title.toLowerCase()}.` }
        : { ok: false, text: "Non hai il permesso per questa azione." },
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
              disabled={!allowed || busy !== null}
              onClick={() => invoke(rung)}
            >
              {!allowed ? "Non autorizzato" : busy === rung.actionType ? "Invio…" : "Esegui"}
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
