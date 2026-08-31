import { NextRequest } from "next/server";

import { ApiError, api } from "@/lib/api";

export const dynamic = "force-dynamic";

/**
 * Recent escalations, so the ladder can report whether a rung was actually
 * carried out rather than merely accepted by the server.
 *
 * "Sent" and "executed" are different facts, and the difference is the whole
 * question the caregiver is asking.
 */
export async function GET(request: NextRequest): Promise<Response> {
  const subjectId = request.nextUrl.searchParams.get("subject");
  if (!subjectId) return new Response("missing subject", { status: 400 });

  try {
    return Response.json(await api.escalations(subjectId));
  } catch (error) {
    const status = error instanceof ApiError ? error.status : 500;
    return new Response("unavailable", { status });
  }
}
