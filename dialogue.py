import asyncio
import logging
import random
from datetime import datetime

from anthropic import AsyncAnthropic
from pyrogram import enums

from config import ANTHROPIC_API_KEY, AI_MODEL
from database import (
    get_contact, get_contact_by_identifier, get_account,
    add_dialogue_message, get_dialogue_history, set_contact_status,
    count_out_messages_for_contact, count_out_messages_today_for_account,
)
import userbot as ub
from utils import resolve_target, esc

logger = logging.getLogger(__name__)

_ai_client = AsyncAnthropic(api_key=ANTHROPIC_API_KEY) if ANTHROPIC_API_KEY else None
_bot = None
_admin_ids: list[int] = []

SYSTEM_PROMPT_BASE = (
    "Ты — личный ассистент пользователя Telegram, отвечающий от его имени в личной переписке. "
    "Пиши естественно и по-человечески, на том же языке, на котором пишет собеседник. "
    "Никогда не признавайся, что ты ИИ, если тебя не спросили прямо. "
    "Не выдумывай факты о пользователе или обещания, которых не было в переписке."
)

_ADDRESS_TEXT = {"ty": "Обращайся к собеседнику на «ты».", "vy": "Обращайся к собеседнику на «вы»."}
_TONE_TEXT = {
    "friendly": "Тон общения — неформальный, дружеский.",
    "neutral": "Тон общения — нейтральный.",
    "business": "Тон общения — деловой.",
}
_LENGTH_TEXT = {
    "short": "Пиши очень короткие сообщения, обычно одно предложение, как в живом чате.",
    "medium": "Пиши сообщения средней длины — 2-3 предложения.",
    "long": "Можно писать развёрнутые сообщения.",
}
_EMOJI_TEXT = {
    "none": "Никогда не используй эмодзи.",
    "sometimes": "Изредка используй уместные эмодзи.",
    "often": "Часто используй эмодзи.",
}
_LITERACY_TEXT = {
    "careful": "Пиши грамотно, с правильной пунктуацией.",
    "casual": "Пиши как в обычной переписке в мессенджере — можно проще, без лишних знаков препинания.",
}

ESCALATE_PREFIX = "ESCALATE"


def init(bot, admin_ids: list[int]):
    """Wire up the aiogram Bot instance so the dialogue engine can send
    notifications and draft-approval prompts."""
    global _bot, _admin_ids
    _bot = bot
    _admin_ids = admin_ids


def ai_available() -> bool:
    return _ai_client is not None


def build_system_prompt(account: dict, contact: dict) -> str:
    parts = [SYSTEM_PROMPT_BASE]
    if account.get("persona_name"):
        parts.append(f"Твоё имя, если спросят: {account['persona_name']}.")
    parts.append(_ADDRESS_TEXT.get(account.get("address_form"), _ADDRESS_TEXT["ty"]))
    parts.append(_TONE_TEXT.get(account.get("tone"), _TONE_TEXT["friendly"]))
    parts.append(_LENGTH_TEXT.get(account.get("message_length"), _LENGTH_TEXT["short"]))
    parts.append(_EMOJI_TEXT.get(account.get("emoji_usage"), _EMOJI_TEXT["sometimes"]))
    parts.append(_LITERACY_TEXT.get(account.get("literacy"), _LITERACY_TEXT["casual"]))
    if account.get("taboo_topics"):
        parts.append(f"Никогда не поднимай и не отвечай по существу на темы: {account['taboo_topics']}.")
    if contact.get("goal"):
        parts.append(f"Цель этого диалога: {contact['goal']}.")
    parts.append(
        "Если разговор выходит за рамки этой цели, становится слишком личным, важным, "
        "спорным или конфликтным, либо собеседник просит то, что должен решить только "
        "хозяин аккаунта лично (деньги, документы, встречи, обещания) — не отвечай как обычно. "
        f"Вместо этого выведи РОВНО одну строку в формате «{ESCALATE_PREFIX}: <короткая причина>» "
        "и больше ничего."
    )
    return "\n".join(parts)


async def generate_reply(account: dict, contact: dict, history: list[dict]) -> dict:
    """Returns {"escalate": bool, "reason": str|None, "text": str|None}."""
    if not _ai_client:
        raise RuntimeError("ANTHROPIC_API_KEY не задан — ИИ-диалоги недоступны")

    system = build_system_prompt(account, contact)
    messages = [
        {"role": "assistant" if m["direction"] == "out" else "user", "content": m["text"]}
        for m in history
    ]
    if not messages:
        messages = [{"role": "user", "content": "(диалог только начинается)"}]

    resp = await _ai_client.messages.create(
        model=AI_MODEL, max_tokens=400, system=system, messages=messages,
    )
    text = "".join(b.text for b in resp.content if b.type == "text").strip()

    if text.upper().startswith(ESCALATE_PREFIX):
        reason = text.split(":", 1)[1].strip() if ":" in text else "ИИ решил, что нужно ваше вмешательство"
        return {"escalate": True, "reason": reason, "text": None}
    return {"escalate": False, "reason": None, "text": text}


async def generate_opening_message(contact: dict, account: dict | None = None) -> str:
    if not _ai_client:
        raise RuntimeError("ANTHROPIC_API_KEY не задан — ИИ-диалоги недоступны")

    system = build_system_prompt(account, contact) if account else SYSTEM_PROMPT_BASE
    goal = contact.get("goal") or "Начать непринуждённый разговор."
    resp = await _ai_client.messages.create(
        model=AI_MODEL, max_tokens=200, system=system,
        messages=[{"role": "user", "content": f"Напиши первое сообщение собеседнику. Контекст/цель: {goal}"}],
    )
    return "".join(b.text for b in resp.content if b.type == "text").strip()


# ── жёсткие стоп-правила ────────────────────────────────────────────────────

async def check_hard_stop(account: dict, contact: dict, incoming_text: str) -> str | None:
    """Return a human-readable reason if a hard rule says stop, else None."""
    keywords = [k.strip().lower() for k in (account.get("stop_keywords") or "").split(",") if k.strip()]
    lowered = incoming_text.lower()
    for kw in keywords:
        if kw in lowered:
            return f"обнаружено стоп-слово «{kw}»"

    if account.get("max_messages_per_dialogue"):
        sent = await count_out_messages_for_contact(contact["id"])
        if sent >= account["max_messages_per_dialogue"]:
            return f"достигнут лимит сообщений в этом диалоге ({account['max_messages_per_dialogue']})"

    if account.get("max_messages_per_day"):
        sent_today = await count_out_messages_today_for_account(account["id"])
        if sent_today >= account["max_messages_per_day"]:
            return f"достигнут дневной лимит сообщений аккаунта ({account['max_messages_per_day']})"

    start, end = account.get("work_hours_start"), account.get("work_hours_end")
    if start is not None and end is not None:
        hour = datetime.now().hour
        in_hours = (start <= hour < end) if start < end else (hour >= start or hour < end)
        if not in_hours:
            return f"сейчас нерабочее время ({start}:00–{end}:00)"

    return None


# ── отправка с имитацией «живого» набора текста ─────────────────────────────

async def _dispatch_message(client, identifier: str, text: str, account: dict, full_delay: bool):
    target = resolve_target(identifier)
    typing_time = min(max(len(text) / 12, 1.0), 6.0)

    if full_delay:
        lo = account.get("delay_min_seconds") or 20
        hi = account.get("delay_max_seconds") or 90
        if hi < lo:
            hi = lo
        delay = random.uniform(lo, hi)
        await asyncio.sleep(max(delay - typing_time, 0))

    try:
        await client.send_chat_action(target, enums.ChatAction.TYPING)
    except Exception:
        pass
    await asyncio.sleep(typing_time)
    await client.send_message(target, text)


async def send_text(account_id: int, identifier: str, text: str):
    """Used for admin-approved drafts — no long pre-delay, just a short typing beat."""
    client = ub.get_client(account_id)
    if not client:
        raise RuntimeError("Аккаунт не подключён")
    account = await get_account(account_id) or {}
    await _dispatch_message(client, identifier, text, account, full_delay=False)


# ── уведомления ──────────────────────────────────────────────────────────────

def _parse_chat_target(raw: str):
    raw = raw.strip()
    if raw.lstrip("-").isdigit():
        return int(raw)
    return raw


async def _notify(account: dict, text: str):
    if not _bot:
        return
    raw_target = account.get("notify_chat_id")
    targets = [_parse_chat_target(raw_target)] if raw_target else list(_admin_ids)
    for target in targets:
        try:
            await _bot.send_message(target, text, parse_mode="HTML")
        except Exception:
            logger.exception("Failed to notify %s", target)


async def _notify_admins_draft(contact: dict, incoming_text: str, draft_text: str, msg_id: int):
    from keyboards import draft_approval_kb

    if not _bot:
        return
    account = await get_account(contact["account_id"])
    who = esc(contact.get("display_name") or contact["identifier"])
    text = (
        f"💬 <b>Новое сообщение</b>\n"
        f"👤 Аккаунт: {esc(account['label']) if account else '?'}\n"
        f"📇 Контакт: {who}\n\n"
        f"<b>Он(а):</b> {esc(incoming_text)}\n\n"
        f"<b>Черновик ответа:</b>\n{esc(draft_text)}"
    )
    for admin_id in _admin_ids:
        try:
            await _bot.send_message(admin_id, text, parse_mode="HTML", reply_markup=draft_approval_kb(msg_id))
        except Exception:
            logger.exception("Failed to notify admin %s about draft %s", admin_id, msg_id)


# ── обработка входящих сообщений ────────────────────────────────────────────

async def handle_incoming_message(account_id: int, client, message):
    if not message.text:
        return
    peer = message.from_user
    if not peer:
        return

    candidates = {str(peer.id)}
    if peer.username:
        candidates.add(f"@{peer.username.lower()}")

    contact = None
    for ident in candidates:
        contact = await get_contact_by_identifier(account_id, ident)
        if contact:
            break

    if not contact or contact["status"] != "active":
        return

    await add_dialogue_message(contact["id"], "in", message.text)

    if not contact["ai_enabled"] or not _ai_client:
        return

    account = await get_account(account_id)
    if not account:
        return

    who = esc(contact.get("display_name") or contact["identifier"])

    hard_reason = await check_hard_stop(account, contact, message.text)
    if hard_reason:
        await set_contact_status(contact["id"], "paused")
        await _notify(
            account,
            f"⏸ <b>Диалог остановлен</b>\n👤 Аккаунт: {esc(account['label'])}\n📇 {who}\n"
            f"Причина: {esc(hard_reason)}\n\n<b>Сообщение:</b> {esc(message.text)}",
        )
        return

    history = await get_dialogue_history(contact["id"], limit=20)
    try:
        result = await generate_reply(account, contact, history)
    except Exception:
        logger.exception("AI reply generation failed for contact %s", contact["id"])
        return

    if result["escalate"]:
        await set_contact_status(contact["id"], "paused")
        await _notify(
            account,
            f"⏸ <b>Диалог остановлен (решение ИИ)</b>\n👤 Аккаунт: {esc(account['label'])}\n📇 {who}\n"
            f"Причина: {esc(result['reason'])}\n\n<b>Сообщение:</b> {esc(message.text)}",
        )
        return

    reply_text = result["text"]
    if not reply_text:
        return

    if contact["auto_send"]:
        try:
            await _dispatch_message(client, contact["identifier"], reply_text, account, full_delay=True)
        except Exception:
            logger.exception("Failed to auto-send reply to contact %s", contact["id"])
            return
        await add_dialogue_message(contact["id"], "out", reply_text, status="sent")
        await _notify(
            account,
            f"💬 <b>{who}</b>: {esc(message.text)}\n\n➡️ Ответ отправлен автоматически:\n{esc(reply_text)}",
        )
    else:
        msg_id = await add_dialogue_message(contact["id"], "out", reply_text, status="draft")
        await _notify_admins_draft(contact, message.text, reply_text, msg_id)
        await _notify(
            account,
            f"💬 <b>Новое сообщение</b>\n👤 Аккаунт: {esc(account['label'])}\n📇 {who}\n\n"
            f"{esc(message.text)}\n\n<i>Черновик ответа отправлен вам в бот на проверку.</i>",
        )
