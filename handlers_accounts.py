from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from config import ADMIN_IDS
from database import get_accounts, get_account
from states import AccountStates
from keyboards import (
    main_menu_kb, accounts_list_kb, account_detail_kb, account_delete_confirm_kb, cancel_kb,
)
import userbot as ub
from handlers_profile import start_profile_wizard
from utils import esc

_TONE_LABELS = {"friendly": "дружеский", "neutral": "нейтральный", "business": "деловой"}
_LENGTH_LABELS = {"short": "короткие", "medium": "средние", "long": "развёрнутые"}
_EMOJI_LABELS = {"none": "не использует", "sometimes": "изредка", "often": "часто"}

router = Router()


def is_admin(uid: int) -> bool:
    return uid in ADMIN_IDS


@router.callback_query(F.data == "accounts_menu")
async def accounts_menu(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return await call.answer()
    await state.clear()
    accounts = await get_accounts()
    if not accounts:
        return await call.message.edit_text(
            "👤 <b>Аккаунты</b>\n\nПока не подключено ни одного аккаунта.",
            parse_mode="HTML",
            reply_markup=accounts_list_kb([]),
        )
    await call.message.edit_text(
        f"👤 <b>Аккаунты ({len(accounts)})</b>\n\nВыберите аккаунт или добавьте новый:",
        parse_mode="HTML",
        reply_markup=accounts_list_kb(accounts),
    )


@router.callback_query(F.data.startswith("acc_view:"))
async def acc_view(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return await call.answer()
    account_id = int(call.data.split(":", 1)[1])
    acc = await get_account(account_id)
    if not acc:
        return await call.answer("Аккаунт не найден", show_alert=True)
    status = "🟢 подключён" if acc["connected"] else "🔴 отключён"

    if acc.get("profile_ready"):
        profile_lines = (
            f"Тон: {_TONE_LABELS.get(acc.get('tone'), '—')} | "
            f"Сообщения: {_LENGTH_LABELS.get(acc.get('message_length'), '—')} | "
            f"Эмодзи: {_EMOJI_LABELS.get(acc.get('emoji_usage'), '—')}\n"
            f"Задержка ответа: {acc.get('delay_min_seconds', 20)}-{acc.get('delay_max_seconds', 90)} сек\n"
            f"Уведомления: {acc.get('notify_chat_id') or 'в этот чат'}"
        )
    else:
        profile_lines = "⚠️ Профиль общения ещё не настроен (используются значения по умолчанию)."

    await call.message.edit_text(
        f"👤 <b>{esc(acc['label'])}</b>\n📱 {esc(acc['phone'])}\nСтатус: {status}\n\n{profile_lines}",
        parse_mode="HTML",
        reply_markup=account_detail_kb(account_id, bool(acc["connected"])),
    )


@router.callback_query(F.data.startswith("acc_disconnect:"))
async def acc_disconnect(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return await call.answer()
    account_id = int(call.data.split(":", 1)[1])
    await ub.disconnect_account(account_id)
    await acc_view(call)


@router.callback_query(F.data.startswith("acc_reconnect:"))
async def acc_reconnect(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return await call.answer()
    account_id = int(call.data.split(":", 1)[1])
    ok = await ub.reconnect_account(account_id)
    if not ok:
        await call.answer("❌ Не удалось переподключить. Возможно, сессия отозвана.", show_alert=True)
    await acc_view(call)


@router.callback_query(F.data.startswith("acc_delete:"))
async def acc_delete(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return await call.answer()
    account_id = int(call.data.split(":", 1)[1])
    acc = await get_account(account_id)
    if not acc:
        return await call.answer("Аккаунт не найден", show_alert=True)
    await call.message.edit_text(
        f"⚠️ Удалить аккаунт <b>{esc(acc['label'])}</b>?\n\n"
        f"Это удалит все связанные диалоги и историю переписки безвозвратно.",
        parse_mode="HTML",
        reply_markup=account_delete_confirm_kb(account_id),
    )


@router.callback_query(F.data.startswith("acc_delete_yes:"))
async def acc_delete_yes(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return await call.answer()
    account_id = int(call.data.split(":", 1)[1])
    await ub.remove_account(account_id)
    await call.answer("Аккаунт удалён")
    await accounts_menu(call, state)


# ── add account flow ──────────────────────────────────────────────────────────

@router.callback_query(F.data == "acc_add")
async def acc_add(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return await call.answer()
    await state.set_state(AccountStates.waiting_label)
    await call.message.edit_text(
        "➕ <b>Добавление аккаунта</b>\n\n"
        "Шаг 1 из 4 — придумайте название для этого аккаунта (например «Личный» или «Рабочий»):",
        parse_mode="HTML", reply_markup=cancel_kb(),
    )


@router.message(AccountStates.waiting_label)
async def acc_got_label(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    label = message.text.strip()
    if not label:
        return await message.answer("❌ Название не может быть пустым. Попробуйте ещё раз:")
    await state.update_data(label=label)
    await message.answer(
        "🔑 <b>Шаг 2 из 4 — API ID</b>\n\nВведите <b>API ID</b> (число с my.telegram.org):",
        parse_mode="HTML", reply_markup=cancel_kb(),
    )
    await state.set_state(AccountStates.waiting_api_id)


@router.message(AccountStates.waiting_api_id)
async def acc_got_api_id(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    raw = message.text.strip()
    if not raw.isdigit():
        return await message.answer("❌ API ID — это число. Попробуйте ещё раз:")
    await state.update_data(api_id=int(raw))
    await message.answer(
        "🔑 <b>Шаг 3 из 4 — API Hash</b>\n\nВведите <b>API Hash</b>:",
        parse_mode="HTML", reply_markup=cancel_kb(),
    )
    await state.set_state(AccountStates.waiting_api_hash)


@router.message(AccountStates.waiting_api_hash)
async def acc_got_api_hash(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    raw = message.text.strip()
    if len(raw) < 10:
        return await message.answer("❌ Слишком короткий. Проверьте и введите снова:")
    await state.update_data(api_hash=raw)
    await message.answer(
        "🔑 <b>Шаг 4 из 4 — Session String</b>\n\n"
        "Введите <b>Session String</b> этого аккаунта.\n\n"
        "Как получить — запустите скрипт <code>generate_session.py</code> на своём компьютере, "
        "войдя под тем номером, который хотите подключить.",
        parse_mode="HTML", reply_markup=cancel_kb(),
    )
    await state.set_state(AccountStates.waiting_session_string)


@router.message(AccountStates.waiting_session_string)
async def acc_got_session_string(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    session_string = message.text.strip()
    data = await state.get_data()
    msg = await message.answer("⏳ Подключаю аккаунт...")
    result = await ub.connect_account(
        label=data["label"], api_id=data["api_id"], api_hash=data["api_hash"],
        session_string=session_string,
    )
    if result.get("ok"):
        await msg.edit_text(
            f"✅ <b>Аккаунт «{esc(data['label'])}» подключён!</b>\n"
            f"👤 {esc(result.get('name',''))} | 📱 {esc(result.get('phone',''))}",
            parse_mode="HTML",
        )
        await start_profile_wizard(message, state, result["account_id"])
    else:
        await msg.edit_text(
            f"❌ Ошибка:\n<code>{result['error']}</code>",
            parse_mode="HTML", reply_markup=cancel_kb(),
        )
