import { redirect } from "next/navigation";

import { PresenceView } from "@/components/PresenceView";
import { BottomNav } from "@/components/BottomNav";
import { Unauthenticated, api } from "@/lib/api";
import { can } from "@/lib/presence";

export default async function PresencePage({
  params,
}: {
  params: Promise<{ subjectId: string }>;
}) {
  const { subjectId } = await params;

  let snapshot;
  let subjects;
  try {
    [snapshot, subjects] = await Promise.all([api.snapshot(subjectId), api.subjects()]);
  } catch (error) {
    if (error instanceof Unauthenticated) redirect("/login");
    throw error;
  }

  const subject = subjects.find((s) => s.id === subjectId);
  const scopes = subject?.scopes ?? [];

  return (
    <main className="shell">
      <div className="topbar">
        <span className="brand">Accanto</span>
        <span className="avatar" aria-hidden="true">
          {(subject?.display_name ?? "?").charAt(0).toUpperCase()}
        </span>
      </div>

      <div className="content">
        <PresenceView
          subjectId={subjectId}
          subjectName={subject?.display_name ?? "Persona"}
          initial={snapshot}
          canSeeLocation={can(scopes, "location:coarse") || can(scopes, "location:precise")}
          canEscalate={can(scopes, "escalation:notify")}
        />
      </div>

      <BottomNav subjectId={subjectId} active="presenza" scopes={scopes} />
    </main>
  );
}
