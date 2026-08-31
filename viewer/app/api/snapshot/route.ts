import { NextRequest } from "next/server";

import { ApiError, api } from "@/lib/api";

export const dynamic = "force-dynamic";

/**
 * Current presence, re-fetched periodically by the open page.
 *
 * The page renders once on the server. With the phone unreachable no events
 * arrive, so without this the headline would sit at whatever was true when the
 * tab was opened -- still reporting "active" an hour later. Polling keeps the
 * backend as the single authority instead of duplicating the fusion rules in
 * the browser, where the two copies would inevitably drift apart.
 */
export async function GET(request: NextRequest): Promise<Response> {
  const subjectId = request.nextUrl.searchParams.get("subject");
  if (!subjectId) return new Response("missing subject", { status: 400 });

  try {
    return Response.json(await api.snapshot(subjectId));
  } catch (error) {
    const status = error instanceof ApiError ? error.status : 500;
    return new Response("unavailable", { status });
  }
}
