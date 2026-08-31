"""ICE servers for a call, including a relay when one is configured.

Without a relay, two peers behind restrictive NAT cannot reach each other at
all -- typically the phone on mobile data and the caregiver elsewhere, which is
the scenario that matters most. STUN alone only works when at least one side is
directly reachable.

Credentials are minted per call and expire. A static TURN password shipped to
every client would be a long-lived shared secret sitting in a browser.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import time
from typing import Any

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)

CREDENTIAL_TTL_SECONDS = 3600
CLOUDFLARE_TURN_API = "https://rtc.live.cloudflare.com/v1/turn/keys/{key_id}/credentials/generate"


async def ice_servers() -> list[dict[str, Any]]:
    """STUN always, plus a relay if one is configured.

    Never raises: a relay that cannot be reached degrades to STUN-only, which
    still connects on many networks. Failing the whole call because the relay
    is down would be worse than a call that works most of the time.
    """
    settings = get_settings()
    servers: list[dict[str, Any]] = [{"urls": settings.stun_urls}]

    relay = await _relay()
    if relay is not None:
        servers.append(relay)
    return servers


async def _relay() -> dict[str, Any] | None:
    settings = get_settings()

    if settings.cloudflare_turn_key_id and settings.cloudflare_turn_token:
        return await _cloudflare_relay(
            settings.cloudflare_turn_key_id, settings.cloudflare_turn_token
        )

    if settings.turn_url and settings.turn_shared_secret:
        return _coturn_relay(settings.turn_url, settings.turn_shared_secret)

    if settings.turn_url and settings.turn_username and settings.turn_credential:
        # Static credentials: workable, but the same secret reaches every
        # client and never expires. Kept for self-hosted setups that predate
        # the shared-secret scheme.
        return {
            "urls": settings.turn_url,
            "username": settings.turn_username,
            "credential": settings.turn_credential,
        }

    logger.info("no TURN relay configured; falling back to STUN only")
    return None


async def _cloudflare_relay(key_id: str, token: str) -> dict[str, Any] | None:
    """Ask Cloudflare for short-lived TURN credentials."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                CLOUDFLARE_TURN_API.format(key_id=key_id),
                headers={"Authorization": f"Bearer {token}"},
                json={"ttl": CREDENTIAL_TTL_SECONDS},
            )
        if response.status_code >= 400:
            logger.warning("Cloudflare TURN refused: %s %s", response.status_code, response.text[:200])
            return None

        body = response.json()
        ice = body.get("iceServers") or body
        urls = ice.get("urls")
        if not urls or not ice.get("username"):
            logger.warning("Cloudflare TURN returned an unexpected shape: %s", list(body))
            return None

        return {
            "urls": urls,
            "username": ice["username"],
            "credential": ice.get("credential"),
        }
    except Exception:
        logger.exception("could not obtain Cloudflare TURN credentials")
        return None


def _coturn_relay(url: str, shared_secret: str) -> dict[str, Any]:
    """The standard coturn REST scheme: username is an expiry, password an HMAC.

    Lets a self-hosted relay accept per-call credentials without the backend
    having to talk to it, and without any long-lived password on the client.
    """
    expiry = int(time.time()) + CREDENTIAL_TTL_SECONDS
    username = str(expiry)
    digest = hmac.new(shared_secret.encode(), username.encode(), hashlib.sha1).digest()
    return {
        "urls": url,
        "username": username,
        "credential": base64.b64encode(digest).decode(),
    }
