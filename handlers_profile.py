from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from config import ADMIN_IDS
from database import get_account, update_account_profile
from states import AccountProfileStates
from keyboards import (
    main_menu_kb,
    profile_address_kb, profile_tone_kb, profile_length_kb,
    profile_emoji_kb, profile_literacy_kb, profile_fallback_kb,
)
import userbot as ub
from utils import esc

router = Router()


def is_admin(uid: int) -> bool:
    return uid in ADMIN_IDS


async def start_profile_wizard(message_target, state: FSMContext, account_id: int):
    """message_target: either a Message or CallbackQuery.message to reply through."""
    await state.update_data(profile_account_id=account_id)
    await state.set_state(AccountProfileStates.waiting_persona_name)
    await message_target.answer(
        "🎭 <b>Настройка профиля общения</b>\n\n"
        "Сейчас настроим, как этот аккаунт будет вести переписку — стиль речи, "
        "границы и когда звать вас на помощь. Отвечайте по очереди, это займёт пару минут.\n\n"
        "1️⃣ Как представляться, если спросят имя? (или «-», чтобы пропустить)",
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("acc_profile:"))
async def acc_profile_entry(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return await call.answer()
    account_id = int(call.data.split(":", 1)[1])
    if not await get_account(account_id):
        return await call.answer("Аккаунт не найден", show_alert=True)
    await start_profile_wizard(call.message, state, account_id)


# ── 1. имя ───────────────────────────────────────────────────────────────────

@router.message(AccountProfileStates.waiting_persona_name)
async def prof_persona_name(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    raw = message.text.strip()
    await state.update_data(persona_name=None if raw == "-" else raw)
    await state.set_state(AccountProfileStates.waiting_address_form)
    await message.answer("2️⃣ Обращение к собеседникам:", reply_markup=profile_address_kb())


# ── 2. ты/вы ─────────────────────────────────────────────────────────────────

@router.callback_query(AccountProfileStates.waiting_address_form, F.data.startswith("prof_addr:"))
async def prof_address(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return await call.answer()
    await state.update_data(address_form=call.data.split(":", 1)[1])
    await state.set_state(AccountProfileStates.waiting_tone)
    await call.message.edit_text("3️⃣ Тон общения:", reply_markup=profile_tone_kb())


# ── 3. тон ───────────────────────────────────────────────────────────────────

@router.callback_query(AccountProfileStates.waiting_tone, F.data.startswith("prof_tone:"))
async def prof_tone(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return await call.answer()
    await state.update_data(tone=call.data.split(":", 1)[1])
    await state.set_state(AccountProfileStates.waiting_message_length)
    await call.message.edit_text("4️⃣ Длина сообщений:", reply_markup=profile_length_kb())


# ── 4. длина сообщений ───────────────────────────────────────────────────────

@router.callback_query(AccountProfileStates.waiting_message_length, F.data.startswith("prof_len:"))
async def prof_length(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return await call.answer()
    await state.update_data(message_length=call.data.split(":", 1)[1])
    await state.set_state(AccountProfileStates.waiting_emoji)
    await call.message.edit_text("5️⃣ Эмодзи в сообщениях:", reply_markup=profile_emoji_kb())


# ── 5. эмодзи ────────────────────────────────────────────────────────────────

@router.callback_query(AccountProfileStates.waiting_emoji, F.data.startswith("prof_emoji:"))
async def prof_emoji(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return await call.answer()
    await state.update_data(emoji_usage=call.data.split(":", 1)[1])
    await state.set_state(AccountProfileStates.waiting_literacy)
    await call.message.edit_text("6️⃣ Стиль письма:", reply_markup=profile_literacy_kb())


# ── 6. грамотность ───────────────────────────────────────────────────────────

@router.callback_query(AccountProfileStates.waiting_literacy, F.data.startswith("prof_lit:"))
async def prof_literacy(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return await call.answer()
    await state.update_data(literacy=call.data.split(":", 1)[1])
    await state.set_state(AccountProfileStates.waiting_taboo_topics)
    await call.message.edit_text(
        "7️⃣ Есть темы, которые нельзя поднимать или отвечать на них? "
        "Опишите через запятую, или «-», чтобы пропустить:"
    )


# ── 7. табу-темы ─────────────────────────────────────────────────────────────

@router.message(AccountProfileStates.waiting_taboo_topics)
async def prof_taboo(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    raw = message.text.strip()
    await state.update_data(taboo_topics=None if raw == "-" else raw)
    await state.set_state(AccountProfileStates.waiting_fallback)
    await message.answer(
        "8️⃣ Что делать, если написали что-то непонятное или неудобное:",
        reply_markup=profile_fallback_kb(),
    )


# ── 8. поведение при затруднении ─────────────────────────────────────────────

@router.callback_query(AccountProfileStates.waiting_fallback, F.data.startswith("prof_fb:"))
async def prof_fallback(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return await call.answer()
    await state.update_data(fallback_behavior=call.data.split(":", 1)[1])
    await state.set_state(AccountProfileStates.waiting_stop_keywords)
    await call.message.edit_text(
        "9️⃣ <b>Стоп-слова</b>\n\n"
        "Если в сообщении собеседника встретится одно из этих слов — бот сразу "
        "остановится и позовёт вас, не отвечая сам. Перечислите через запятую "
        "(например: <code>встреча, оплата, карта, пароль</code>) или «-»:",
        parse_mode="HTML",
    )


# ── 9. стоп-слова ────────────────────────────────────────────────────────────

@router.message(AccountProfileStates.waiting_stop_keywords)
async def prof_stop_keywords(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    raw = message.text.strip()
    await state.update_data(stop_keywords=None if raw == "-" else raw)
    await state.set_state(AccountProfileStates.waiting_msg_limit_dialogue)
    await message.answer(
        "🔟 Максимум сообщений от бота <b>в одном диалоге</b>, после которого он "
        "останавливается и зовёт вас? Введите число или «-» — без лимита:",
        parse_mode="HTML",
    )


# ── 10. лимит сообщений в диалоге ────────────────────────────────────────────

@router.message(AccountProfileStates.waiting_msg_limit_dialogue)
async def prof_limit_dialogue(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    raw = message.text.strip()
    value = None
    if raw != "-":
        if not raw.isdigit():
            return await message.answer("❌ Введите число или «-»:")
        value = int(raw)
    await state.update_data(max_messages_per_dialogue=value)
    await state.set_state(AccountProfileStates.waiting_msg_limit_day)
    await message.answer(
        "1️⃣1️⃣ Максимум сообщений от бота <b>в сутки</b> по этому аккаунту (по всем диалогам)? "
        "Число или «-» — без лимита:",
        parse_mode="HTML",
    )


# ── 11. дневной лимит ────────────────────────────────────────────────────────

@router.message(AccountProfileStates.waiting_msg_limit_day)
async def prof_limit_day(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    raw = message.text.strip()
    value = None
    if raw != "-":
        if not raw.isdigit():
            return await message.answer("❌ Введите число или «-»:")
        value = int(raw)
    await state.update_data(max_messages_per_day=value)
    await state.set_state(AccountProfileStates.waiting_work_hours)
    await message.answer(
        "1️⃣2️⃣ Часы, в которые бот может отвечать (по времени сервера), формат "
        "<code>9-22</code>. Или «-» — без ограничений:",
        parse_mode="HTML",
    )


# ── 12. рабочие часы ─────────────────────────────────────────────────────────

@router.message(AccountProfileStates.waiting_work_hours)
async def prof_work_hours(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    raw = message.text.strip()
    start = end = None
    if raw != "-":
        try:
            a, b = raw.split("-")
            start, end = int(a), int(b)
            assert 0 <= start <= 23 and 0 <= end <= 23
        except Exception:
            return await message.answer("❌ Формат: <code>9-22</code> или «-»:", parse_mode="HTML")
    await state.update_data(work_hours_start=start, work_hours_end=end)
    await state.set_state(AccountProfileStates.waiting_notify_chat)
    await message.answer(
        "1️⃣3️⃣ <b>Канал уведомлений</b>\n\n"
        "Куда слать уведомления о новых сообщениях и об остановках диалога? "
        "Перешлите сюда любое сообщение из канала/группы, или введите его "
        "@username / числовой ID. «-» — уведомления пойдут вам в личку с ботом:",
        parse_mode="HTML",
    )


# ── 13. канал уведомлений ────────────────────────────────────────────────────

@router.message(AccountProfileStates.waiting_notify_chat)
async def prof_notify_chat(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    forwarded_chat = getattr(message, "forward_from_chat", None)
    chat_id = None
    if forwarded_chat:
        chat_id = str(forwarded_chat.id)
    else:
        raw = (message.text or "").strip()
        if raw and raw != "-":
            chat_id = raw
    await state.update_data(notify_chat_id=chat_id)
    await state.set_state(AccountProfileStates.waiting_delay_range)
    await message.answer(
        "1️⃣4️⃣ <b>Задержка перед ответом</b>\n\n"
        "Диапазон в секундах, например <code>30-180</code> — бот будет ждать "
        "случайное время из этого диапазона и показывать «печатает…» перед отправкой. "
        "«-» — использовать значение по умолчанию (20-90 сек):",
        parse_mode="HTML",
    )


# ── 14. задержка ─────────────────────────────────────────────────────────────

@router.message(AccountProfileStates.waiting_delay_range)
async def prof_delay_range(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    raw = message.text.strip()
    delay_min = delay_max = None
    if raw != "-":
        try:
            a, b = raw.split("-")
            delay_min, delay_max = int(a), int(b)
            assert 0 <= delay_min <= delay_max
        except Exception:
            return await message.answer("❌ Формат: <code>30-180</code> или «-»:", parse_mode="HTML")
    await state.update_data(delay_min_seconds=delay_min, delay_max_seconds=delay_max)
    await _finish_wizard(message, state)


_PROFILE_FIELDS = [
    "persona_name", "address_form", "tone", "message_length", "emoji_usage", "literacy",
    "taboo_topics", "fallback_behavior", "stop_keywords",
    "max_messages_per_dialogue", "max_messages_per_day",
    "work_hours_start", "work_hours_end", "notify_chat_id",
    "delay_min_seconds", "delay_max_seconds",
]


async def _finish_wizard(message: Message, state: FSMContext):
    data = await state.get_data()
    account_id = data["profile_account_id"]

    update_fields = {k: data[k] for k in _PROFILE_FIELDS if k in data}
    update_fields["profile_ready"] = 1
    await update_account_profile(account_id, **update_fields)
    await state.clear()

    account = await get_account(account_id)
    label = esc(account["label"])
    await message.answer(
        f"✅ <b>Профиль для «{label}» настроен!</b>\n\n"
        f"Можно менять его в любой момент через «👤 Аккаунты → {label} → 🎭 Профиль общения».",
        parse_mode="HTML",
        reply_markup=main_menu_kb(ub.is_connected()),
    )
