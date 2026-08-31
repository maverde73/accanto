import { NextRequest } from "next/server";

import { API_URL } from "@/lib/api";
import { readToken } from "@/lib/session";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

/** SSE proxy.
 *
 * The browser's EventSource cannot set an Authorization header, and putting the
 * token in the URL would hand a credential for health and location data to
 * JavaScript, the browser history and every proxy in between. So the stream is
 * relayed here: the token is attached server-side and never leaves this process.
 */
export async function GET(request: NextRequest): Promise<Response> {
  const token = await readToken();
  if (!token) return new Response("unauthenticated", { status: 401 });

  const subjectId = request.nextUrl.searchParams.get("subject");
  if (!subjectId) return new Response("missing subject", { status: 400 });

  const upstream = await fetch(
    `${API_URL}/v1/realtime/sse?subject_id=${encodeURIComponent(subjectId)}`,
    {
      headers: { Authorization: `Bearer ${token}`, Accept: "text/event-stream" },
      // Close the upstream stream as soon as the browser goes away, instead of
      // leaving an orphaned subscriber on the backend's hub.
      signal: request.signal,
      cache: "no-store",
    },
  );

  if (!upstream.ok || upstream.body === null) {
    return new Response("stream unavailable", { status: upstream.status || 502 });
  }

  return new Response(upstream.body, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
      "X-Accel-Buffering": "no",
    },
  });
}
