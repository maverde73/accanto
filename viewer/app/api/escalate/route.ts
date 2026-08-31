import { NextRequest } from "next/server";

import { ApiError, api } from "@/lib/api";

export const dynamic = "force-dynamic";

/** Invokes one rung of the escalation ladder.
 *
 * The rung's required scope is enforced by the backend, which refuses with 403
 * if the grant does not cover it. Hiding a button here is a courtesy to the
 * caregiver; the refusal is what actually protects the subject.
 */
export async function POST(request: NextRequest): Promise<Response> {
  const subjectId = request.nextUrl.searchParams.get("subject");
  if (!subjectId) return new Response("missing subject", { status: 400 });

  let body: { action_type?: unknown; params?: unknown };
  try {
    body = (await request.json()) as typeof body;
  } catch {
    return new Response("invalid body", { status: 400 });
  }

  if (typeof body.action_type !== "string") {
    return new Response("missing action_type", { status: 400 });
  }

  try {
    const result = await api.escalate(
      subjectId,
      body.action_type,
      (body.params as Record<string, unknown>) ?? {},
    );
    return Response.json(result, { status: 202 });
  } catch (error) {
    if (error instanceof ApiError) {
      return Response.json({ detail: error.message }, { status: error.status });
    }
    return new Response("escalation failed", { status: 500 });
  }
}
