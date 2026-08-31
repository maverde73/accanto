import { redirect } from "next/navigation";

import { ApiError, login } from "@/lib/api";
import { startSession } from "@/lib/session";

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string }>;
}) {
  const params = await searchParams;

  async function submit(formData: FormData) {
    "use server";

    const email = String(formData.get("email") ?? "");
    const password = String(formData.get("password") ?? "");

    try {
      const token = await login(email, password);
      await startSession(token);
    } catch (error) {
      // Never distinguish "unknown address" from "wrong password" in the UI
      // either: the backend deliberately does not, and echoing more here would
      // undo it.
      const tooMany = error instanceof ApiError && error.status === 429;
      redirect(`/login?error=${tooMany ? "rate" : "credentials"}`);
    }
    redirect("/");
  }

  return (
    <main className="login">
      <div>
        <h1 style={{ fontSize: 26, margin: 0 }}>Accanto</h1>
        <p className="muted" style={{ marginTop: 6 }}>
          Accedi per vedere come sta la persona che segui.
        </p>
      </div>

      <form action={submit} style={{ display: "flex", flexDirection: "column", gap: 14 }}>
        <div className="field">
          <label htmlFor="email">Email</label>
          <input id="email" name="email" type="email" autoComplete="username" required />
        </div>
        <div className="field">
          <label htmlFor="password">Password</label>
          <input
            id="password"
            name="password"
            type="password"
            autoComplete="current-password"
            required
          />
        </div>

        {params.error === "credentials" ? (
          <p className="error">Credenziali non valide.</p>
        ) : null}
        {params.error === "rate" ? (
          <p className="error">Troppi tentativi. Riprova tra qualche minuto.</p>
        ) : null}

        <button className="btn btn-primary" type="submit">
          Entra
        </button>
      </form>
    </main>
  );
}
