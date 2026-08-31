import { NextRequest } from "next/server";

import { ApiError, api } from "@/lib/api";

export const dynamic = "force-dynamic";

/** Starts a check-in on behalf of the signed-in caregiver.
 *
 * A thin proxy so the client component never needs the session token. The
 * backend still re-checks the caller's scopes: this route is a convenience, not
 * the security boundary.
 */
export async function POST(request: NextRequest): Promise<Response> {
  const subjectId = request.nextUrl.searchParams.get("subject");
  if (!subjectId) return new Response("missing subject", { status: 400 });

  try {
    const checkin = await api.requestCheckin(subjectId);
    return Response.json(checkin, { status: 202 });
  } catch (error) {
    const status = error instanceof ApiError ? error.status : 500;
    return new Response("check-in failed", { status });
  }
}
