"""Push transport to the collector.

The payload deliberately carries only an identifier and a type. Details are
fetched over authenticated HTTPS, so intercepting or forging a push cannot by
itself make a phone ring or open its microphone.
"""

from __future__ import annotations

import logging
import uuid
from typing import Protocol

logger = logging.getLogger(__name__)


class PushSender(Protocol):
    async def send_command(self, fcm_token: str, command_id: uuid.UUID, action_type: str) -> bool:
        """Wake the collector. Returns whether the transport accepted it."""
        ...


class LoggingPushSender:
    """Development sender: records what would have been sent.

    Used whenever FCM credentials are absent, so the whole command flow can be
    exercised end to end without a Firebase project.
    """

    def __init__(self) -> None:
        self.sent: list[tuple[str, uuid.UUID, str]] = []

    async def send_command(self, fcm_token: str, command_id: uuid.UUID, action_type: str) -> bool:
        self.sent.append((fcm_token, command_id, action_type))
        logger.info("push (dev): command=%s type=%s token=%s…", command_id, action_type, fcm_token[:8])
        return True


class FcmPushSender:
    """Real FCM sender. Imported lazily so firebase-admin stays optional."""

    def __init__(self, credentials_path: str) -> None:
        self._credentials_path = credentials_path
        self._app = None

    def _ensure_app(self) -> None:
        if self._app is not None:
            return
        import firebase_admin  # noqa: PLC0415
        from firebase_admin import credentials  # noqa: PLC0415

        self._app = firebase_admin.initialize_app(
            credentials.Certificate(self._credentials_path), name="accanto"
        )

    async def send_command(self, fcm_token: str, command_id: uuid.UUID, action_type: str) -> bool:
        from firebase_admin import messaging  # noqa: PLC0415

        self._ensure_app()
        message = messaging.Message(
            token=fcm_token,
            data={"command_id": str(command_id), "type": action_type},
            android=messaging.AndroidConfig(priority="high"),
        )
        try:
            messaging.send(message, app=self._app)
            return True
        except Exception:
            logger.exception("FCM send failed for command %s", command_id)
            return False


_sender: PushSender | None = None


def get_push_sender() -> PushSender:
    global _sender
    if _sender is None:
        from app.core.config import get_settings  # noqa: PLC0415

        path = get_settings().fcm_credentials_path
        _sender = FcmPushSender(path) if path else LoggingPushSender()
    return _sender


def set_push_sender(sender: PushSender | None) -> None:
    """Override the sender (tests, or an alternative transport)."""
    global _sender
    _sender = sender
