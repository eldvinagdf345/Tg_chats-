import os
from pyrogram import Client
from database import save_session, disconnect_session, clear_session, get_session_info
from pyrogram import Client, filters
from pyrogram.handlers import MessageHandler
from database import (
    create_account, get_accounts, get_account,
    set_account_connected, delete_account,
)

SESSION_NAME = "userbot_session"
_clients: dict[int, Client] = {}
_incoming_handler = None  # set via set_incoming_handler(); called for every private text message

_userbot: Client | None = None
_is_connected = False

def set_incoming_handler(callback):
    """callback(account_id: int, client: Client, message) -> coroutine"""
    global _incoming_handler
    _incoming_handler = callback

def get_userbot() -> Client | None:
    return _userbot

def _register_handlers(account_id: int, client: Client):
    async def _on_private_message(client, message):
        if _incoming_handler:
            await _incoming_handler(account_id, client, message)

    client.add_handler(MessageHandler(_on_private_message, filters.private & filters.incoming & filters.text))


def get_client(account_id: int) -> Client | None:
    return _clients.get(account_id)


def is_connected() -> bool:
    return _is_connected and _userbot is not None
    return len(_clients) > 0


async def start_userbot_from_string(session_string: str, api_id: int, api_hash: str) -> bool:
    global _userbot, _is_connected
async def connect_account(label: str, api_id: int, api_hash: str, session_string: str) -> dict:
    try:
        _userbot = Client(
            name=SESSION_NAME,
        client = Client(
            name=f"account_new_{label}",
            api_id=api_id,
            api_hash=api_hash,
            session_string=session_string,
            in_memory=True,
        )
        await _userbot.start()
        me = await _userbot.get_me()
        _is_connected = True
        await save_session(
            phone=me.phone_number or "unknown",
            api_id=str(api_id),
            api_hash=api_hash,
        await client.start()
        me = await client.get_me()
        account_id = await create_account(
            label=label, phone=me.phone_number or "unknown",
            api_id=api_id, api_hash=api_hash, session_string=session_string,
        )
        return True
        _clients[account_id] = client
        _register_handlers(account_id, client)
        return {"ok": True, "account_id": account_id, "name": me.first_name, "phone": me.phone_number}
    except Exception as e:
        _userbot = None
        _is_connected = False
        return False
        return {"error": f"[{type(e).__name__}] {e}"}


async def start_userbot(api_id: int, api_hash: str) -> bool:
    """Restore from session string env var or saved session file."""
    global _userbot, _is_connected
    if _is_connected and _userbot:
        return True
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

    session_string = os.getenv("SESSION_STRING", "").strip()
    if session_string:
        return await start_userbot_from_string(session_string, api_id, api_hash)

    # Fallback: try session file
async def _start_client_for(acc: dict) -> bool:
    try:
        _userbot = Client(SESSION_NAME, api_id=api_id, api_hash=api_hash)
        await _userbot.start()
        _is_connected = True
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
        _userbot = None
        _is_connected = False
        await set_account_connected(acc["id"], False)
        return False


async def reconnect_account(account_id: int) -> bool:
    if account_id in _clients:
        return True
    acc = await get_account(account_id)
    if not acc:
        return False
    return await _start_client_for(acc)


async def stop_userbot():
    global _userbot, _is_connected
    if _userbot:
async def disconnect_account(account_id: int):
    client = _clients.pop(account_id, None)
    if client:
        try:
            await _userbot.stop()
            await client.stop()
        except Exception:
            pass
    _userbot = None
    _is_connected = False
    await disconnect_session()


async def full_disconnect():
    await stop_userbot()
    await clear_session()
    for ext in ("", ".session"):
        path = SESSION_NAME + ext
        if os.path.exists(path):
            os.remove(path)
    await set_account_connected(account_id, False)


# ── Авторизация через session string (из бота) ────────────────────────────────

async def auth_via_session_string(session_string: str, api_id: int, api_hash: str) -> dict:
    """Connect using a pre-generated session string."""
    global _userbot, _is_connected
    try:
        client = Client(
            name=SESSION_NAME,
            api_id=api_id,
            api_hash=api_hash,
            session_string=session_string,
        )
        await client.start()
        me = await client.get_me()
        _userbot = client
        _is_connected = True
        await save_session(
            phone=me.phone_number or "unknown",
            api_id=str(api_id),
            api_hash=api_hash,
        )
        return {"ok": True, "name": me.first_name, "phone": me.phone_number}
    except Exception as e:
        return {"error": f"[{type(e).__name__}] {str(e)}"}
async def remove_account(account_id: int):
    await disconnect_account(account_id)
    await delete_account(account_id)
