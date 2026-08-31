import Link from "next/link";
import { redirect } from "next/navigation";

import { BottomNav } from "@/components/BottomNav";
import { LocationMap } from "@/components/LocationMap";
import { Unauthenticated, api } from "@/lib/api";

export default async function MapPage({
  params,
}: {
  params: Promise<{ subjectId: string }>;
}) {
  const { subjectId } = await params;

  let subjects;
  let location = null;
  try {
    subjects = await api.subjects();
    location = await api.latestLocation(subjectId);
  } catch (error) {
    if (error instanceof Unauthenticated) redirect("/login");
    throw error;
  }

  const subject = subjects.find((s) => s.id === subjectId);
  if (!subject) redirect("/");

  return (
    <main className="shell">
      <div className="topbar">
        <Link href={`/s/${subjectId}`} className="brand">
          ← Accanto
        </Link>
      </div>
      <div className="content">
        <h1 style={{ fontSize: 22, margin: 0 }}>Dov'è {subject.display_name}</h1>
        <LocationMap subjectId={subjectId} initial={location} />
      </div>
      <BottomNav subjectId={subjectId} active="mappa" scopes={subject.scopes} />
    </main>
  );
}
