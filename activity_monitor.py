import asyncio
import logging

from database import get_stale_active_contacts, set_contacts_bucket, get_account
import events

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
                accounts_cache = {}
                for c in stale:
                    if c["account_id"] not in accounts_cache:
                        accounts_cache[c["account_id"]] = await get_account(c["account_id"])
                    acc = accounts_cache[c["account_id"]]
                    events.emit(
                        "system",
                        account=acc.get("label") if acc else None,
                        contact=c.get("display_name") or c["identifier"],
                        text="перемещён в «Корзину» — нет ответа дольше тайм-аута",
                    )
        except Exception:
            logger.exception("Activity monitor sweep failed")
        await asyncio.sleep(CHECK_INTERVAL_SECONDS)
