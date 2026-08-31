import Link from "next/link";
import { redirect } from "next/navigation";

import { BottomNav } from "@/components/BottomNav";
import { EscalationLadder } from "@/components/EscalationLadder";
import { Unauthenticated, api } from "@/lib/api";

export default async function ContactPage({
  params,
}: {
  params: Promise<{ subjectId: string }>;
}) {
  const { subjectId } = await params;

  let subjects;
  try {
    subjects = await api.subjects();
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
        <h1 style={{ fontSize: 22, margin: 0 }}>Serve contattarlo?</h1>
        <EscalationLadder subjectId={subjectId} scopes={subject.scopes} />
      </div>
      <BottomNav subjectId={subjectId} active="contatto" scopes={subject.scopes} />
    </main>
  );
}
