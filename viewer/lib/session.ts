import "server-only";

import { cookies } from "next/headers";

/** Session handling.
 *
 * The backend token lives in an httpOnly cookie and is read only on the server.
 * It is never sent to the browser, so an XSS in this app cannot walk away with
 * a credential for someone's health and location data -- which is also why the
 * live stream is proxied SSE rather than a browser WebSocket carrying the token
 * in its URL.
 */

const COOKIE = "accanto_session";

export async function readToken(): Promise<string | null> {
  const store = await cookies();
  return store.get(COOKIE)?.value ?? null;
}

export async function startSession(token: string, maxAgeSeconds = 900): Promise<void> {
  const store = await cookies();
  store.set(COOKIE, token, {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.ACCANTO_SECURE_COOKIES === "1",
    path: "/",
    maxAge: maxAgeSeconds,
  });
}

export async function endSession(): Promise<void> {
  const store = await cookies();
  store.delete(COOKIE);
}
