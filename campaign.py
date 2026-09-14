import asyncio
import logging
import random

from database import (
    get_account, get_contact_by_identifier, create_contact, add_dialogue_message,
)
import userbot as ub
import dialogue as dlg
from utils import normalize_identifier, resolve_target

logger = logging.getLogger(__name__)

_running: dict[int, asyncio.Task] = {}
_progress: dict[int, dict] = {}


def is_running(account_id: int) -> bool:
    return account_id in _running


def get_progress(account_id: int) -> dict | None:
    return _progress.get(account_id)


def start_campaign(account_id: int, usernames: list[str]) -> bool:
    """Starts dialogues with everyone in `usernames`, relying entirely on the
    account's own instructions/persona — no per-campaign goal or send-mode,
    those are already configured on the account. New contacts always start
    in draft-review mode (safe default)."""
    if account_id in _running:
        return False
    task = asyncio.create_task(_run(account_id, usernames))
    _running[account_id] = task
    return True


def stop_campaign(account_id: int) -> bool:
    task = _running.pop(account_id, None)
    _progress.pop(account_id, None)
    if task:
        task.cancel()
        return True
    return False


async def _run(account_id: int, usernames: list[str]):
    _progress[account_id] = {"sent": 0, "skipped": 0, "total": len(usernames)}
    try:
        for raw in usernames:
            if account_id not in _running:
                return

            client = ub.get_client(account_id)
            if not client:
                return

            identifier = normalize_identifier(raw)
            if await get_contact_by_identifier(account_id, identifier):
                _progress[account_id]["skipped"] += 1
                continue

            account = await get_account(account_id)
            if not account:
                return

            try:
                if dlg.ai_available():
                    opening = await dlg.generate_opening_message({}, account)
                else:
                    opening = "Привет!"
            except Exception:
                logger.exception("Campaign: failed to generate opening for %s", identifier)
                continue

            try:
                await client.send_message(resolve_target(identifier), opening)
            except Exception:
                logger.exception("Campaign: failed to send to %s", identifier)
                continue

            contact_id = await create_contact(
                account_id=account_id, identifier=identifier, auto_send=False,
            )
            await add_dialogue_message(contact_id, "out", opening, status="sent")
            _progress[account_id]["sent"] += 1

            lo = account.get("campaign_interval_min_seconds") or 300
            hi = account.get("campaign_interval_max_seconds") or 900
            if hi < lo:
                hi = lo
            await asyncio.sleep(random.uniform(lo, hi))
    finally:
        _running.pop(account_id, None)
        _progress.pop(account_id, None)
