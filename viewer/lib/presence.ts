/** Turning a snapshot into what the caregiver reads.
 *
 * Two rules from docs/03-liveness-model.md are enforced here, in code:
 *
 *  - Absence of data is grey ("I don't know"), never an alarm. A caregiver who
 *    learns that red can mean "the watch is charging" stops trusting red.
 *  - Colour never carries meaning alone: every state also has a label and an
 *    icon, for colour-blind readers and for glanceability.
 *
 * State labels are gender-neutral on purpose: the subject's name is
 * configurable, and "Maurizio · Attiva" is wrong Italian.
 */

import type { HeadlineState, Snapshot, Tone } from "@/lib/types";
import { duration, isFresh, relative } from "@/lib/time";

export interface HeadlineView {
  label: string;
  tone: Tone;
  detail: string | null;
  timeLabel: string | null;
}

export interface ClockRow {
  key: "interaction" | "movement" | "vital" | "contact";
  tierLabel: string;
  title: string;
  at: string | null;
  tone: Tone;
  note: string | null;
}

/** Freshness windows, mirroring the backend defaults. */
export const FRESH_MINUTES = {
  interaction: 15,
  movement: 15,
  vital: 20,
  contact: 30,
} as const;

const STATE_LABEL: Record<HeadlineState, string> = {
  active: "In attività",
  moving: "In movimento",
  vitals_only: "A riposo",
  quiet: "Silenzio",
  no_data: "Nessun dato",
};

const STATE_TONE: Record<HeadlineState, Tone> = {
  active: "green",
  moving: "green",
  vitals_only: "amber",
  quiet: "amber",
  no_data: "grey",
};

export function toneOf(state: HeadlineState): Tone {
  return STATE_TONE[state];
}

export function labelOf(state: HeadlineState): string {
  return STATE_LABEL[state];
}

export function headlineView(snapshot: Snapshot, now: Date = new Date()): HeadlineView {
  const { state, at } = snapshot.headline;
  const tone = STATE_TONE[state] ?? "grey";

  let label = STATE_LABEL[state] ?? "Nessun dato";
  if (state === "quiet") label = `Silenzio da ${duration(at, now)}`;

  return {
    label,
    tone,
    detail: detailFor(snapshot, now),
    timeLabel: at ? relative(at, now) : null,
  };
}

function detailFor(snapshot: Snapshot, now: Date): string | null {
  const { state, at, evidence } = snapshot.headline;

  if (state === "no_data") {
    // Explain the silence rather than leaving a bare grey dot. Most of the time
    // the honest answer is mundane, and saying so is what keeps the amber and
    // red states meaningful.
    return snapshot.batteries.watch_likely_charging
      ? "Nessun dato recente — l'orologio è probabilmente in carica"
      : "Nessun dato recente — potrebbe essere un problema di collegamento";
  }

  if (state === "vitals_only") return "Nessun movimento, ma i parametri sono normali";

  if (evidence && at) return `${capitalise(evidence)} ${relative(at, now)}`;
  return evidence ? capitalise(evidence) : null;
}

export function clockRows(snapshot: Snapshot, now: Date = new Date()): ClockRow[] {
  const { clocks, vitals, batteries } = snapshot;

  return [
    {
      key: "interaction",
      tierLabel: "Interazione",
      title: interactionTitle(snapshot),
      at: clocks.interaction,
      tone: freshTone(clocks.interaction, FRESH_MINUTES.interaction, now),
      note: null,
    },
    {
      key: "movement",
      // With no clock at all, "In movimento" would assert something that never
      // happened. A row title has to be able to say "nothing arrived".
      title: clocks.movement === null ? "Nessun movimento ricevuto" : "In movimento",
      tierLabel: "Movimento",
      at: clocks.movement,
      tone: freshTone(clocks.movement, FRESH_MINUTES.movement, now),
      note: null,
    },
    {
      key: "vital",
      tierLabel: "Segni vitali",
      // The last known value is always shown, however old, alongside its age.
      // Hiding a reading for being stale is the app deciding for the caregiver:
      // "68, two hours ago" is something they can weigh, and it is also how
      // they tell a quiet watch from a broken pipeline. Whether it counts as
      // evidence of presence is a separate question, answered by the tone.
      title:
        vitals.bpm !== null
          ? `Battito ${vitals.bpm}`
          : clocks.vital !== null
            ? "Battito rilevato"
            : "Nessun battito ricevuto",
      at: clocks.vital,
      tone: freshTone(clocks.vital, FRESH_MINUTES.vital, now),
      note: batteries.watch_likely_charging ? "Orologio probabilmente in carica" : null,
    },
    {
      key: "contact",
      tierLabel: "Contatto di sistema",
      title:
        batteries.phone_pct === null
          ? "Telefono raggiungibile"
          : `Telefono carico ${batteries.phone_pct}%`,
      at: clocks.contact,
      // Always neutral, never green. System contact proves the pipeline works,
      // not that the person is well; giving it the same colour as real evidence
      // would let a merely reachable phone read as reassuring.
      tone: "grey",
      note: null,
    },
  ];
}

function interactionTitle(snapshot: Snapshot): string {
  const { state, evidence } = snapshot.headline;
  // Only reuse the headline's evidence when interaction is what produced it;
  // otherwise the row would claim a precision the snapshot does not carry.
  if (state === "active" && evidence) return capitalise(evidence);
  return "Ha usato il telefono";
}

function freshTone(at: string | null, windowMinutes: number, now: Date): Tone {
  return isFresh(at, windowMinutes, now) ? "green" : "grey";
}

function capitalise(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1);
}

/** Whether the caregiver is allowed to see something, given their grant. */
export function can(scopes: string[], scope: string): boolean {
  return scopes.includes(scope);
}

export const COLLECTOR_SILENT_MINUTES = 12;

/**
 * Whether the phone has stopped reporting altogether.
 *
 * Distinct from the person being quiet, and it has to be, because the
 * consequences differ: a quiet person may be fine, but an unreachable phone
 * means every button on this page will do nothing. Saying "sent" and then
 * staying silent is the exact failure this product exists to prevent.
 *
 * The heartbeat runs every five minutes, so twelve allows two to be missed
 * before the alarm is raised.
 */
export function collectorUnreachable(snapshot: Snapshot, now: Date = new Date()): boolean {
  return !isFresh(snapshot.clocks.contact, COLLECTOR_SILENT_MINUTES, now);
}
