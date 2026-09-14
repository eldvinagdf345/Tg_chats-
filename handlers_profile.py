from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from config import ADMIN_IDS
from database import get_account, get_contact, update_account_profile
from states import InstructionsChatStates, QuickSettingStates
from keyboards import (
    account_settings_kb, instructions_chat_kb, instructions_reset_confirm_kb, setting_edit_kb,
)
import instructions_chat
import dialogue as dlg
from utils import esc

router = Router()


def is_admin(uid: int) -> bool:
    return uid in ADMIN_IDS


# ═══════════════════════════════════════════════════════════════════════════════
#  СВОБОДНЫЙ ЧАТ ИНСТРУКЦИЙ
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("instr_open:"))
async def instr_open(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return await call.answer()
    account_id = int(call.data.split(":", 1)[1])
    if not await get_account(account_id):
        return await call.answer("Аккаунт не найден", show_alert=True)
    if not instructions_chat.ai_available():
        return await call.answer("⚠️ ANTHROPIC_API_KEY не настроен на сервере.", show_alert=True)

    await state.set_state(InstructionsChatStates.chatting)
    await state.update_data(instr_account_id=account_id)
    await call.message.edit_text(
        "📝 <b>Задать инструкции</b>\n\n"
        "Опишите своими словами, как ассистент должен вести переписку: приветствие, стиль "
        "речи, что говорить в разных ситуациях, когда останавливаться и звать вас. Можно "
        "писать по частям в несколько сообщений — каждое дополнит общую картину, а не "
        "перезапишет её. Пишите:",
        parse_mode="HTML",
        reply_markup=instructions_chat_kb(account_id),
    )


@router.callback_query(F.data.startswith("fix_pattern:"))
async def fix_pattern_open(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return await call.answer()
    contact_id = int(call.data.split(":", 1)[1])
    contact = await get_contact(contact_id)
    if not contact:
        return await call.answer("Диалог не найден", show_alert=True)
    if not instructions_chat.ai_available():
        return await call.answer("⚠️ ANTHROPIC_API_KEY не настроен на сервере.", show_alert=True)

    await state.set_state(InstructionsChatStates.chatting)
    await state.update_data(instr_account_id=contact["account_id"], retry_contact_id=contact_id)
    await call.message.reply(
        "📝 Опишите, как нужно было ответить на это сообщение. Это дополнит общие инструкции "
        "аккаунта, после чего диалог возобновится и бот попробует ответить снова:",
    )


@router.message(InstructionsChatStates.chatting)
async def instr_got_message(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    if not message.text:
        return await message.answer("Пришлите текстовое сообщение.")
    data = await state.get_data()
    account_id = data["instr_account_id"]
    retry_contact_id = data.get("retry_contact_id")
    msg = await message.answer("⏳ Обновляю инструкции...")
    try:
        result = await instructions_chat.update_instructions(account_id, message.text.strip())
    except Exception as e:
        return await msg.edit_text(f"❌ Ошибка ИИ:\n<code>{esc(e)}</code>", parse_mode="HTML")

    if retry_contact_id:
        await state.clear()
        outcome = await dlg.retry_after_instruction(retry_contact_id)
        return await msg.edit_text(
            f"{esc(result['reply'])}\n\n{outcome}", parse_mode="HTML",
        )

    await msg.edit_text(
        f"{esc(result['reply'])}\n\nМожете продолжать писать, или нажмите «Готово».",
        parse_mode="HTML",
        reply_markup=instructions_chat_kb(account_id),
    )


@router.callback_query(F.data.startswith("instr_show:"))
async def instr_show(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return await call.answer()
    account_id = int(call.data.split(":", 1)[1])
    account = await get_account(account_id)
    if not account:
        return await call.answer("Аккаунт не найден", show_alert=True)
    text = account.get("custom_instructions") or "Пока ничего не задано."
    await call.message.answer(
        f"📄 <b>Текущие инструкции:</b>\n\n{esc(text)}",
        parse_mode="HTML", reply_markup=instructions_chat_kb(account_id),
    )


@router.callback_query(F.data.startswith("instr_reset:"))
async def instr_reset(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return await call.answer()
    account_id = int(call.data.split(":", 1)[1])
    await call.message.edit_text(
        "⚠️ Стереть все инструкции для этого аккаунта? Отменить будет нельзя.",
        reply_markup=instructions_reset_confirm_kb(account_id),
    )


@router.callback_query(F.data.startswith("instr_reset_yes:"))
async def instr_reset_yes(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return await call.answer()
    account_id = int(call.data.split(":", 1)[1])
    await update_account_profile(account_id, custom_instructions=None)
    await call.answer("Инструкции очищены")
    await state.set_state(InstructionsChatStates.chatting)
    await state.update_data(instr_account_id=account_id)
    await call.message.edit_text(
        "🗑 Инструкции очищены. Начните описывать заново:",
        reply_markup=instructions_chat_kb(account_id),
    )


# ═══════════════════════════════════════════════════════════════════════════════
#  НАСТРОЙКИ (жёсткие правила, тайминг, уведомления)
# ═══════════════════════════════════════════════════════════════════════════════

def _text_parser(column):
    def parser(raw):
        return {column: None if raw == "-" else raw}
    return parser


def _int_parser(column):
    def parser(raw):
        if raw == "-":
            return {column: None}
        if not raw.isdigit():
            return None
        return {column: int(raw)}
    return parser


def _range_parser(col_lo, col_hi):
    def parser(raw):
        if raw == "-":
            return {col_lo: None, col_hi: None}
        try:
            a, b = raw.split("-")
            lo, hi = int(a.strip()), int(b.strip())
            assert 0 <= lo <= hi
        except Exception:
            return None
        return {col_lo: lo, col_hi: hi}
    return parser


def _hours_parser(raw):
    if raw == "-":
        return {"work_hours_start": None, "work_hours_end": None}
    try:
        a, b = raw.split("-")
        start, end = int(a.strip()), int(b.strip())
        assert 0 <= start <= 23 and 0 <= end <= 23
    except Exception:
        return None
    return {"work_hours_start": start, "work_hours_end": end}


_SETTINGS = {
    "stop_keywords": {
        "title": "Стоп-слова",
        "prompt": (
            "Перечислите через запятую слова/темы, при которых бот сразу останавливается "
            "и зовёт вас, например: <code>встреча, оплата, карта, пароль</code>. Или «-», "
            "чтобы убрать:"
        ),
        "parser": _text_parser("stop_keywords"),
    },
    "max_messages_per_dialogue": {
        "title": "Лимит сообщений за диалог",
        "prompt": "Максимум ответов бота в одном диалоге, после которого он останавливается. Число, или «-» — без лимита:",
        "parser": _int_parser("max_messages_per_dialogue"),
    },
    "max_messages_per_day": {
        "title": "Лимит сообщений за сутки",
