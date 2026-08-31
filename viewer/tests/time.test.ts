import { describe, expect, it } from "vitest";

import { clock, duration, isFresh, relative } from "@/lib/time";

const NOW = new Date("2026-06-15T12:40:00+02:00");

function minutesAgo(n: number): Date {
  return new Date(NOW.getTime() - n * 60_000);
}

describe("relative", () => {
  it("reads as 'adesso' under a minute", () => {
    expect(relative(minutesAgo(0), NOW)).toBe("adesso");
    expect(relative(minutesAgo(0.5), NOW)).toBe("adesso");
  });

  it("agrees in number for a single minute", () => {
    expect(relative(minutesAgo(1), NOW)).toBe("1 minuto fa");
    expect(relative(minutesAgo(4), NOW)).toBe("4 minuti fa");
  });

  it("switches to a clock time after an hour", () => {
    expect(relative(minutesAgo(90), NOW)).toBe("alle 11:10");
  });

  it("names yesterday", () => {
    expect(relative(new Date("2026-06-14T23:10:00+02:00"), NOW)).toBe("ieri alle 23:10");
  });

  it("spells out older dates in Italian", () => {
    expect(relative(new Date("2026-06-03T09:00:00+02:00"), NOW)).toBe("il 3 giugno alle 09:00");
  });

  it("treats a fast device clock as 'adesso' rather than the future", () => {
    // A phone running a few seconds ahead must not produce "fra 2 minuti".
    expect(relative(new Date(NOW.getTime() + 120_000), NOW)).toBe("adesso");
  });

  it("says 'mai' when there is nothing", () => {
    expect(relative(null, NOW)).toBe("mai");
  });
});

describe("clock", () => {
  it("pads to two digits", () => {
    expect(clock(new Date("2026-06-15T09:05:00+02:00"))).toBe("09:05");
  });
});

describe("duration", () => {
  it("reports minutes under an hour", () => {
    expect(duration(minutesAgo(34), NOW)).toBe("34 min");
  });

  it("reports hours and minutes", () => {
    expect(duration(minutesAgo(135), NOW)).toBe("2h 15m");
  });

  it("drops the minutes when they are zero", () => {
    expect(duration(minutesAgo(120), NOW)).toBe("2h");
  });

  it("never goes negative on clock skew", () => {
    expect(duration(new Date(NOW.getTime() + 60_000), NOW)).toBe("0 min");
  });
});

describe("isFresh", () => {
  it("includes the boundary", () => {
    expect(isFresh(minutesAgo(15), 15, NOW)).toBe(true);
    expect(isFresh(minutesAgo(16), 15, NOW)).toBe(false);
  });

  it("treats missing data as not fresh", () => {
    expect(isFresh(null, 15, NOW)).toBe(false);
  });
});
