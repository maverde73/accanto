import { describe, expect, it } from "vitest";

import { clockRows, headlineView, labelOf, toneOf } from "@/lib/presence";
import type { HeadlineState, Snapshot } from "@/lib/types";

const NOW = new Date("2026-06-15T12:40:00+02:00");

function iso(minutesAgo: number): string {
  return new Date(NOW.getTime() - minutesAgo * 60_000).toISOString();
}

function snapshot(overrides: Partial<Snapshot> = {}): Snapshot {
  return {
    subject_id: "s1",
    computed_at: iso(0),
    headline: {
      state: "active",
      color: "green",
      at: iso(4),
      evidence_kind: "unlock",
      evidence: "ha sbloccato il telefono",
    },
    clocks: { interaction: iso(4), movement: iso(9), vital: iso(12), contact: iso(1) },
    vitals: { bpm: 72, bpm_at: iso(12) },
    batteries: { phone_pct: 88, watch_likely_charging: false },
    pipeline: { lag_seconds_p90: 30, healthy: true },
    ...overrides,
  };
}

describe("state labels", () => {
  it("carry no adjective that agrees with the subject", () => {
    // The subject's name is configurable, so "Maurizio · Attiva" is wrong
    // Italian. Every label is built from a noun phrase instead, which reads
    // correctly whoever is being monitored. Asserted literally: whether a word
    // is an agreeing adjective is not something a pattern can decide
    // ("movimento" ends in -o and is perfectly neutral).
    expect(labelOf("active")).toBe("In attività");
    expect(labelOf("moving")).toBe("In movimento");
    expect(labelOf("vitals_only")).toBe("A riposo");
    expect(labelOf("quiet")).toBe("Silenzio");
    expect(labelOf("no_data")).toBe("Nessun dato");
  });

  it("covers every state the backend can send", () => {
    const states: HeadlineState[] = ["active", "moving", "vitals_only", "quiet", "no_data"];
    for (const state of states) expect(labelOf(state)).toBeTruthy();
  });
});

describe("tones", () => {
  it("maps activity to green", () => {
    expect(toneOf("active")).toBe("green");
    expect(toneOf("moving")).toBe("green");
  });

  it("maps quiet-but-known to amber", () => {
    expect(toneOf("vitals_only")).toBe("amber");
    expect(toneOf("quiet")).toBe("amber");
  });

  it("maps absence of data to grey, never red", () => {
    expect(toneOf("no_data")).toBe("grey");
  });

  it("never produces red from a headline state", () => {
    // Red is reserved for the positive presence of a problem, raised by the
    // alert engine. A caregiver who learns red can mean "watch on charger"
    // stops trusting red.
    const states: HeadlineState[] = ["active", "moving", "vitals_only", "quiet", "no_data"];
    for (const state of states) expect(toneOf(state)).not.toBe("red");
  });
});

describe("headlineView", () => {
  it("shows the evidence and when it happened", () => {
    const view = headlineView(snapshot(), NOW);
    expect(view.label).toBe("In attività");
    expect(view.tone).toBe("green");
    expect(view.detail).toBe("Ha sbloccato il telefono 4 minuti fa");
    expect(view.timeLabel).toBe("4 minuti fa");
  });

  it("puts the silence duration in the label", () => {
    const view = headlineView(
      snapshot({
        headline: { state: "quiet", color: "amber", at: iso(135), evidence_kind: null, evidence: null },
      }),
      NOW,
    );
    expect(view.label).toBe("Silenzio da 2h 15m");
    expect(view.tone).toBe("amber");
  });

  it("explains no_data instead of leaving a bare grey dot", () => {
    const view = headlineView(
      snapshot({
        headline: { state: "no_data", color: "grey", at: null, evidence_kind: null, evidence: null },
        batteries: { phone_pct: null, watch_likely_charging: true },
      }),
      NOW,
    );
    expect(view.tone).toBe("grey");
    expect(view.detail).toContain("probabilmente in carica");
  });

  it("hedges the charging guess rather than stating it", () => {
    const view = headlineView(
      snapshot({
        headline: { state: "no_data", color: "grey", at: null, evidence_kind: null, evidence: null },
        batteries: { phone_pct: null, watch_likely_charging: true },
      }),
      NOW,
    );
    // It is an inference from a data gap, not a fact the watch reported.
    expect(view.detail).toMatch(/probabilmente/);
  });
});

describe("clockRows", () => {
  it("returns the four tiers in order of evidential strength", () => {
    const rows = clockRows(snapshot(), NOW);
    expect(rows.map((r) => r.key)).toEqual(["interaction", "movement", "vital", "contact"]);
  });

  it("colours a tier green only while its clock is fresh", () => {
    const rows = clockRows(snapshot(), NOW);
    expect(rows[0]?.tone).toBe("green");

    const stale = clockRows(
      snapshot({ clocks: { interaction: iso(120), movement: iso(120), vital: iso(120), contact: iso(1) } }),
      NOW,
    );
    // The mockup drew every tile green; left literal, a silent system would
    // still look reassuring while the headline said otherwise.
    expect(stale[0]?.tone).toBe("grey");
    expect(stale[1]?.tone).toBe("grey");
    expect(stale[2]?.tone).toBe("grey");
  });

  it("never colours system contact green", () => {
    const rows = clockRows(snapshot(), NOW);
    expect(rows[3]?.tone).toBe("grey");
  });

  it("shows the heart rate when it is permitted", () => {
    expect(clockRows(snapshot(), NOW)[2]?.title).toBe("Battito 72");
  });

  it("does not claim a heartbeat that never arrived", () => {
    // Found in the first real end-to-end run: with no watch data at all the row
    // still read "Battito rilevato", asserting something that never happened.
    const rows = clockRows(
      snapshot({
        clocks: { interaction: iso(2), movement: null, vital: null, contact: iso(1) },
        vitals: { bpm: null, bpm_at: null },
      }),
      NOW,
    );
    expect(rows[2]?.title).toBe("Nessun battito ricevuto");
    expect(rows[1]?.title).toBe("Nessun movimento ricevuto");
  });

  it("degrades gracefully when vitals are withheld by scope", () => {
    // A caregiver without `vitals` still sees that a heartbeat was observed --
    // that is presence, not a health record.
    const rows = clockRows(snapshot({ vitals: { bpm: null, bpm_at: null } }), NOW);
    expect(rows[2]?.title).toBe("Battito rilevato");
    expect(rows[2]?.at).not.toBeNull();
  });

  it("still shows a heart rate that is hours old", () => {
    // Withholding it would be the app deciding for the caregiver. The value
    // carries its age, and the grey tone says it is no longer evidence.
    const rows = clockRows(
      snapshot({
        clocks: { interaction: iso(200), movement: null, vital: iso(180), contact: iso(1) },
        vitals: { bpm: 68, bpm_at: iso(180) },
      }),
      NOW,
    );
    expect(rows[2]?.title).toBe("Battito 68");
    expect(rows[2]?.at).not.toBeNull();
    expect(rows[2]?.tone).toBe("grey");
  });

  it("flags a probable charge on the vitals row", () => {
    const rows = clockRows(
      snapshot({ batteries: { phone_pct: 88, watch_likely_charging: true } }),
      NOW,
    );
    expect(rows[2]?.note).toMatch(/in carica/);
  });

  it("does not claim a precise interaction it cannot back up", () => {
    // The snapshot carries the evidence kind only for the winning tier, so the
    // interaction row must stay generic when something else won.
    const rows = clockRows(
      snapshot({
        headline: { state: "moving", color: "green", at: iso(2), evidence_kind: "activity", evidence: "si sta muovendo" },
      }),
      NOW,
    );
    expect(rows[0]?.title).toBe("Ha usato il telefono");
  });
});
