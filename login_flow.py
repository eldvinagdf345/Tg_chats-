import logging

from pyrogram import Client
from pyrogram.errors import (
    PhoneNumberInvalid, PhoneCodeInvalid, PhoneCodeExpired,
    SessionPasswordNeeded, PasswordHashInvalid, FloodWait,
)

logger = logging.getLogger(__name__)

# admin_telegram_id -> {"client": Client, "phone": str, "phone_code_hash": str}
# One in-progress phone login per admin at a time.
_pending: dict[int, dict] = {}


async def start_login(admin_id: int, api_id: int, api_hash: str, phone: str) -> dict:
    await cancel_login(admin_id)
    client = Client(name=f"login_{admin_id}", api_id=api_id, api_hash=api_hash, in_memory=True)
    try:
        await client.connect()
        sent = await client.send_code(phone)
    except PhoneNumberInvalid:
        await _safe_disconnect(client)
        return {"error": "Неверный номер телефона."}
    except FloodWait as e:
        await _safe_disconnect(client)
        return {"error": f"Слишком много попыток, подождите {e.value} сек."}
    except Exception as e:
        await _safe_disconnect(client)
        return {"error": f"[{type(e).__name__}] {e}"}

    _pending[admin_id] = {"client": client, "phone": phone, "phone_code_hash": sent.phone_code_hash}
    return {"ok": True}


async def submit_code(admin_id: int, code: str) -> dict:
    state = _pending.get(admin_id)
    if not state:
        return {"error": "Сессия входа истекла. Начните добавление аккаунта заново."}
    client = state["client"]
    try:
        await client.sign_in(state["phone"], state["phone_code_hash"], code)
    except SessionPasswordNeeded:
        return {"need_password": True}
    except (PhoneCodeInvalid, PhoneCodeExpired):
        await cancel_login(admin_id)
        return {"error": "Неверный или истёкший код. Начните добавление аккаунта заново."}
    except Exception as e:
        await cancel_login(admin_id)
        return {"error": f"[{type(e).__name__}] {e}"}
    return await _finalize(admin_id)


async def submit_password(admin_id: int, password: str) -> dict:
    state = _pending.get(admin_id)
    if not state:
        return {"error": "Сессия входа истекла. Начните добавление аккаунта заново."}
    client = state["client"]
    try:
        await client.check_password(password)
    except PasswordHashInvalid:
        return {"error": "Неверный пароль, попробуйте ещё раз."}
    except Exception as e:
        await cancel_login(admin_id)
        return {"error": f"[{type(e).__name__}] {e}"}
    return await _finalize(admin_id)


async def _finalize(admin_id: int) -> dict:
    state = _pending.pop(admin_id)
    client = state["client"]
    session_string = await client.export_session_string()
    me = await client.get_me()
    await _safe_disconnect(client)
    return {
        "ok": True, "session_string": session_string,
        "name": me.first_name, "phone": me.phone_number,
    }


async def cancel_login(admin_id: int):
    state = _pending.pop(admin_id, None)
    if state:
        await _safe_disconnect(state["client"])


async def _safe_disconnect(client: Client):
    try:
        await client.disconnect()
    except Exception:
        logger.exception("Failed to disconnect login client")
