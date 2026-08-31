"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

import { clockRows, headlineView } from "@/lib/presence";
import { relative } from "@/lib/time";
import type { ClockRow } from "@/lib/presence";
import type { Snapshot } from "@/lib/types";
import { BatteryIcon, ChevronIcon, HeartIcon, LockIcon, MotionIcon } from "@/components/icons";

const ICONS = {
  interaction: LockIcon,
  movement: MotionIcon,
  vital: HeartIcon,
  contact: BatteryIcon,
} as const;

interface Props {
  subjectId: string;
  subjectName: string;
  initial: Snapshot;
  canSeeLocation: boolean;
  canEscalate: boolean;
}

export function PresenceView({
  subjectId,
  subjectName,
  initial,
  canSeeLocation,
  canEscalate,
}: Props) {
  const [snapshot, setSnapshot] = useState(initial);
  const [now, setNow] = useState(() => new Date());
  const [checkin, setCheckin] = useState<"idle" | "sending" | "waiting" | "done" | "failed">("idle");

  // Relative labels ("4 minuti fa") go stale on their own, with no new data
  // arriving. Re-render on a timer so the page never quietly lies about age.
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 20_000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    const source = new EventSource(`/api/stream?subject=${encodeURIComponent(subjectId)}`);

    source.addEventListener("snapshot", (event) => {
      const data = JSON.parse((event as MessageEvent<string>).data) as Partial<Snapshot["headline"]> &
        Record<string, unknown>;
      setSnapshot((current) => mergeSnapshot(current, data));
      setNow(new Date());
    });

    source.addEventListener("checkin", (event) => {
      const data = JSON.parse((event as MessageEvent<string>).data) as { status?: string };
      if (data.status === "partial") setCheckin("waiting");
      if (data.status === "answered") setCheckin("done");
    });

    return () => source.close();
  }, [subjectId]);

  const view = headlineView(snapshot, now);
  const rows = clockRows(snapshot, now);

  async function requestCheckin() {
    setCheckin("sending");
    const response = await fetch(`/api/checkin?subject=${encodeURIComponent(subjectId)}`, {
      method: "POST",
    });
    setCheckin(response.ok ? "waiting" : "failed");
  }

  return (
    <>
      <div style={{ display: "flex", flexDirection: "column", gap: 2, paddingTop: 6 }}>
        <div className="subject-name">{subjectName}</div>
        <div className={`headline tone-${view.tone}`}>
          <div className="headline-state">
            <span className="dot" />
            <span className="headline-label">{view.label}</span>
          </div>
          {view.timeLabel ? <span className="headline-time">{view.timeLabel}</span> : null}
        </div>
        {view.detail ? <div className="headline-detail">{view.detail}</div> : null}
      </div>

      {!snapshot.pipeline.healthy ? (
        <div className="banner tone-grey">
          <div className="banner-title">Aggiornamenti in ritardo</div>
          I dati stanno arrivando più lentamente del solito. Non è un allarme sulla persona:
          riguarda il collegamento.
        </div>
      ) : null}

      <div className="card list">
        {rows.map((row, index) => (
          <div key={row.key}>
            {index > 0 ? <div className="row-divider" /> : null}
            <ClockRowView row={row} now={now} />
          </div>
        ))}
      </div>

      <CheckinStatus state={checkin} />

      <div className="actions">
        <button className="btn btn-primary" onClick={requestCheckin} disabled={checkin === "sending"}>
          {checkin === "sending" ? "Invio…" : "Come sta?"}
        </button>
        {canSeeLocation ? (
          <Link className="btn btn-secondary" href={`/s/${subjectId}/mappa`}>
            Sulla mappa
          </Link>
        ) : null}
      </div>

      {canEscalate ? (
        <Link className="nav-card" href={`/s/${subjectId}/contatto`}>
          <div>
            <div className="nav-card-title">Serve contattarlo?</div>
            <div className="nav-card-sub">Scala di escalation · 5 gradini</div>
          </div>
          <span style={{ color: "var(--green)" }}>
            <ChevronIcon />
          </span>
        </Link>
      ) : null}
    </>
  );
}

function ClockRowView({ row, now }: { row: ClockRow; now: Date }) {
  const Icon = ICONS[row.key];
  return (
    <div className={`row tone-${row.tone}`}>
      <div className="tile">
        <Icon />
      </div>
      <div className="row-body">
        <div className="row-title">{row.title}</div>
        <div className="row-meta">
          {row.tierLabel} · {row.at ? relative(row.at, now) : "nessun dato"}
        </div>
        {row.note ? <div className="row-note">{row.note}</div> : null}
      </div>
    </div>
  );
}

function CheckinStatus({ state }: { state: string }) {
  if (state === "idle") return null;

  // The answer arrives in two parts: the phone-side signals within seconds, the
  // fresh heart rate once the forced sync completes. Saying so avoids the
  // impression that nothing is happening.
  const messages: Record<string, string> = {
    sending: "Richiesta inviata…",
    waiting: "Segnali del telefono ricevuti. Attendo il battito aggiornato dall'orologio…",
    done: "Risposta completa ricevuta.",
    failed: "Non è stato possibile inviare la richiesta.",
  };

  return (
    <div className={`banner ${state === "failed" ? "tone-amber" : "tone-green"}`}>
      {messages[state]}
    </div>
  );
}

function mergeSnapshot(current: Snapshot, incoming: Record<string, unknown>): Snapshot {
  const str = (key: string): string | null => {
    const value = incoming[key];
    return typeof value === "string" ? value : null;
  };

  return {
    ...current,
    headline: {
      ...current.headline,
      state: (incoming["headline_state"] as Snapshot["headline"]["state"]) ?? current.headline.state,
      color: (incoming["headline_color"] as string) ?? current.headline.color,
      at: str("headline_at"),
      evidence_kind: str("headline_evidence"),
      evidence: (incoming["headline_evidence_label"] as string | null) ?? current.headline.evidence,
    },
    clocks: {
      interaction: str("last_interaction_at"),
      movement: str("last_movement_at"),
      vital: str("last_vital_at"),
      contact: str("last_contact_at"),
    },
    vitals: {
      bpm: typeof incoming["latest_bpm"] === "number" ? incoming["latest_bpm"] : current.vitals.bpm,
      bpm_at: current.vitals.bpm_at,
    },
    batteries: {
      ...current.batteries,
      watch_likely_charging:
        typeof incoming["watch_likely_charging"] === "boolean"
          ? incoming["watch_likely_charging"]
          : current.batteries.watch_likely_charging,
    },
  };
}
