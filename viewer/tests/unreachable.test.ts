import { describe, expect, it } from "vitest";

import { COLLECTOR_SILENT_MINUTES, collectorUnreachable } from "@/lib/presence";
import type { Snapshot } from "@/lib/types";

const NOW = new Date("2026-06-15T12:40:00+02:00");

function iso(minutesAgo: number): string {
  return new Date(NOW.getTime() - minutesAgo * 60_000).toISOString();
}

function snapshot(contact: string | null): Snapshot {
  return {
    subject_id: "s1",
    computed_at: iso(0),
    headline: { state: "quiet", color: "amber", at: iso(30), evidence_kind: null, evidence: null },
    clocks: { interaction: iso(30), movement: null, vital: null, contact },
    vitals: { bpm: null, bpm_at: null },
    batteries: { phone_pct: 80, watch_likely_charging: false },
    pipeline: { lag_seconds_p90: 20, healthy: true },
  };
}

describe("collectorUnreachable", () => {
  it("is false while heartbeats keep arriving", () => {
    expect(collectorUnreachable(snapshot(iso(3)), NOW)).toBe(false);
  });

  it("tolerates two missed heartbeats before raising it", () => {
    // The heartbeat runs every five minutes; a single missed one is noise.
    expect(collectorUnreachable(snapshot(iso(9)), NOW)).toBe(false);
    expect(collectorUnreachable(snapshot(iso(COLLECTOR_SILENT_MINUTES - 1)), NOW)).toBe(false);
    expect(collectorUnreachable(snapshot(iso(COLLECTOR_SILENT_MINUTES + 1)), NOW)).toBe(true);
  });

  it("is true once the phone has gone quiet", () => {
    expect(collectorUnreachable(snapshot(iso(30)), NOW)).toBe(true);
  });

  it("is true when there has never been any contact", () => {
    expect(collectorUnreachable(snapshot(null), NOW)).toBe(true);
  });

  it("is independent of whether the person is active", () => {
    // The distinction is the point: a quiet person may be perfectly fine, but an
    // unreachable phone means every command the caregiver sends does nothing.
    // Reporting "sent" in that state is the failure this product exists to avoid.
    const personQuietPhoneFine = snapshot(iso(2));
    expect(collectorUnreachable(personQuietPhoneFine, NOW)).toBe(false);
  });
});
