import { redirect } from "next/navigation";

import { Unauthenticated, api } from "@/lib/api";

export default async function Home() {
  let subjects;
  try {
    subjects = await api.subjects();
  } catch (error) {
    if (error instanceof Unauthenticated) redirect("/login");
    throw error;
  }

  if (subjects.length === 0) {
    return (
      <main className="shell">
        <div className="content">
          <h1 style={{ fontSize: 22 }}>Nessuna persona da seguire</h1>
          <p className="muted">
            Non hai autorizzazioni attive. Chiedi a chi amministra il profilo di concedertele.
          </p>
        </div>
      </main>
    );
  }

  const first = subjects[0];
  if (subjects.length === 1 && first) redirect(`/s/${first.id}`);

  return (
    <main className="shell">
      <div className="topbar">
        <span className="brand">Accanto</span>
      </div>
      <div className="content">
        <h1 style={{ fontSize: 22, margin: 0 }}>Chi vuoi vedere?</h1>
        {subjects.map((subject) => (
          <a key={subject.id} className="nav-card" href={`/s/${subject.id}`}>
            <div>
              <div className="nav-card-title">{subject.display_name}</div>
              <div className="nav-card-sub">{subject.scopes.length} permessi attivi</div>
            </div>
          </a>
        ))}
      </div>
    </main>
  );
}
