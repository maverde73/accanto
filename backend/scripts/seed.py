"""Creates a caregiver, a subject and a pending device, then prints the code.

Development helper. Idempotent: re-running reuses the existing user and subject
and only mints a fresh pairing code, so it is safe to call again after a code
has expired.

    ACCANTO_DATABASE_URL=... .venv/bin/python scripts/seed.py
"""

from __future__ import annotations

import asyncio
import os
import sys

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.auth import hash_password  # noqa: E402
from app.models.identity import AppUser, Subject  # noqa: E402
from app.services.devices import DeviceService  # noqa: E402

EMAIL = os.getenv("SEED_EMAIL", "caregiver@example.com")
PASSWORD = os.getenv("SEED_PASSWORD", "accanto-dev-password")
SUBJECT_NAME = os.getenv("SEED_SUBJECT", "Maurizio")


async def main() -> None:
    url = os.environ["ACCANTO_DATABASE_URL"]
    engine = create_async_engine(url)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as session:
        user = (
            await session.execute(select(AppUser).where(AppUser.email == EMAIL))
        ).scalars().first()
        if user is None:
            user = AppUser(
                email=EMAIL, display_name="Caregiver", password_hash=hash_password(PASSWORD)
            )
            session.add(user)
            await session.flush()

        subject = (
            await session.execute(select(Subject).where(Subject.owner_user_id == user.id))
        ).scalars().first()
        if subject is None:
            subject = Subject(
                display_name=SUBJECT_NAME, owner_user_id=user.id, timezone="Europe/Rome", config={}
            )
            session.add(subject)
            await session.flush()

        device, code, expires_at = await DeviceService(session).create_pending(
            subject.id, "phone_collector", "Galaxy S24 Ultra"
        )
        await session.commit()

        print("caregiver :", EMAIL, "/", PASSWORD)
        print("subject   :", subject.display_name, subject.id)
        print("device    :", device.id)
        print("CODICE    :", code)
        print("scade     :", expires_at.isoformat())

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
