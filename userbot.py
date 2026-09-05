from pyrogram import Client, filters
from pyrogram.handlers import MessageHandler
from database import (
    create_account, get_accounts, get_account,
    set_account_connected, delete_account,
)

_clients: dict[int, Client] = {}
_incoming_handler = None  # set via set_incoming_handler(); called for every private text message


def set_incoming_handler(callback):
    """callback(account_id: int, client: Client, message) -> coroutine"""
    global _incoming_handler
    _incoming_handler = callback


def _register_handlers(account_id: int, client: Client):
    async def _on_private_message(client, message):
        if _incoming_handler:
            await _incoming_handler(account_id, client, message)

    client.add_handler(MessageHandler(_on_private_message, filters.private & filters.incoming & filters.text))


def get_client(account_id: int) -> Client | None:
    return _clients.get(account_id)


def get_userbot() -> Client | None:
    """First connected account — used by the channel-parsing feature, which
    is single-account by design."""
    return next(iter(_clients.values()), None)


def is_connected() -> bool:
    return len(_clients) > 0


async def connect_account(label: str, api_id: int, api_hash: str, session_string: str) -> dict:
    try:
        client = Client(
            name=f"account_new_{label}",
            api_id=api_id,
            api_hash=api_hash,
            session_string=session_string,
            in_memory=True,
        )
        await client.start()
        me = await client.get_me()
        account_id = await create_account(
            label=label, phone=me.phone_number or "unknown",
            api_id=api_id, api_hash=api_hash, session_string=session_string,
        )
        _clients[account_id] = client
        _register_handlers(account_id, client)
        return {"ok": True, "account_id": account_id, "name": me.first_name, "phone": me.phone_number}
    except Exception as e:
        return {"error": f"[{type(e).__name__}] {e}"}


async def start_saved_accounts() -> int:
    """Reconnect every account saved in the DB that isn't already live.
    Called on bot startup."""
    started = 0
    for acc in await get_accounts():
        if acc["id"] in _clients:
            continue
        if await _start_client_for(acc):
            started += 1
    return started


async def _start_client_for(acc: dict) -> bool:
    try:
        client = Client(
            name=f"account_{acc['id']}",
            api_id=int(acc["api_id"]),
            api_hash=acc["api_hash"],
            session_string=acc["session_string"],
            in_memory=True,
        )
        await client.start()
        _clients[acc["id"]] = client
        _register_handlers(acc["id"], client)
        await set_account_connected(acc["id"], True)
        return True
    except Exception:
        await set_account_connected(acc["id"], False)
        return False


async def reconnect_account(account_id: int) -> bool:
    if account_id in _clients:
        return True
    acc = await get_account(account_id)
    if not acc:
        return False
    return await _start_client_for(acc)


async def disconnect_account(account_id: int):
    client = _clients.pop(account_id, None)
    if client:
        try:
            await client.stop()
        except Exception:
            pass
    await set_account_connected(account_id, False)


async def remove_account(account_id: int):
    await disconnect_account(account_id)
    await delete_account(account_id)
