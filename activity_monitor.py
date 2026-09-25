import asyncio
import logging

from database import get_stale_active_contacts, set_contacts_bucket

logger = logging.getLogger(__name__)

CHECK_INTERVAL_SECONDS = 900  # 15 минут


async def run():
    """Background sweep: moves contacts out of "Активные" into "Корзина"
    once they've gone quiet past their account's inactivity timeout. The
    contact and its history are never deleted, so if they write again the
    dialogue picks back up (see dialogue.handle_incoming_message)."""
    while True:
        try:
            stale = await get_stale_active_contacts()
            if stale:
                await set_contacts_bucket([c["id"] for c in stale], "trash")
                logger.info("Moved %d inactive contact(s) to Корзина", len(stale))
        except Exception:
            logger.exception("Activity monitor sweep failed")
        await asyncio.sleep(CHECK_INTERVAL_SECONDS)
