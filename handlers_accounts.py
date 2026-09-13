from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from config import ADMIN_IDS
from database import get_accounts, get_account
from states import AccountStates
from keyboards import (
    main_menu_kb, accounts_list_kb, account_detail_kb, account_delete_confirm_kb, cancel_kb,
    auth_method_kb,
)
import userbot as ub
import login_flow
from utils import esc

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

    if acc.get("custom_instructions"):
        profile_lines = "📝 Инструкции заданы."
    else:
        profile_lines = "⚠️ Инструкции ещё не заданы — «📝 Задать инструкции» ниже."

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
        "🔑 <b>Шаг 4 из 4 — вход в аккаунт</b>\n\nКак подключим?",
        parse_mode="HTML", reply_markup=auth_method_kb(),
    )


@router.callback_query(F.data == "auth_session_string")
async def auth_choose_session_string(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return await call.answer()
    await state.set_state(AccountStates.waiting_session_string)
    await call.message.edit_text(
        "✍️ Введите <b>Session String</b> этого аккаунта.\n\n"
        "Как получить — запустите скрипт <code>generate_session.py</code> на своём компьютере, "
        "войдя под тем номером, который хотите подключить.",
        parse_mode="HTML", reply_markup=cancel_kb(),
    )


@router.callback_query(F.data == "auth_phone")
async def auth_choose_phone(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return await call.answer()
    await state.set_state(AccountStates.waiting_phone)
    await call.message.edit_text(
        "📱 Введите номер телефона в международном формате, например <code>+79991234567</code>:",
        parse_mode="HTML", reply_markup=cancel_kb(),
    )


@router.message(AccountStates.waiting_phone)
async def acc_got_phone(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    phone = message.text.strip()
    data = await state.get_data()
    msg = await message.answer("⏳ Отправляю код...")
    result = await login_flow.start_login(message.from_user.id, data["api_id"], data["api_hash"], phone)
    if result.get("error"):
        return await msg.edit_text(
            f"❌ {esc(result['error'])}\n\nПопробуйте ввести номер ещё раз:", parse_mode="HTML",
        )
    await state.update_data(phone=phone)
    await state.set_state(AccountStates.waiting_phone_code)
    await msg.edit_text(
        "💬 Код отправлен в Telegram на этот номер (посмотрите сообщение от <b>Telegram</b> "
        "в приложении — не в этом боте). Введите полученный код:",
        parse_mode="HTML",
    )


@router.message(AccountStates.waiting_phone_code)
async def acc_got_phone_code(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    code = message.text.strip().replace(" ", "")
    msg = await message.answer("⏳ Проверяю код...")
    result = await login_flow.submit_code(message.from_user.id, code)
    if result.get("need_password"):
        await state.set_state(AccountStates.waiting_2fa_password)
        return await msg.edit_text(
            "🔒 На аккаунте включён облачный пароль (двухфакторка). Введите пароль:",
        )
    if result.get("error"):
        await state.clear()
        return await msg.edit_text(
            f"❌ {esc(result['error'])}", parse_mode="HTML", reply_markup=cancel_kb(),
        )
    await _finish_phone_login(message, state, msg, result)


@router.message(AccountStates.waiting_2fa_password)
async def acc_got_2fa_password(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    password = message.text.strip()
    msg = await message.answer("⏳ Проверяю пароль...")
    result = await login_flow.submit_password(message.from_user.id, password)
    if result.get("error"):
        return await msg.edit_text(f"❌ {esc(result['error'])}", parse_mode="HTML")
    await _finish_phone_login(message, state, msg, result)


async def _finish_phone_login(message: Message, state: FSMContext, msg: Message, login_result: dict):
    data = await state.get_data()
    conn = await ub.connect_account(
        label=data["label"], api_id=data["api_id"], api_hash=data["api_hash"],
        session_string=login_result["session_string"],
    )
    if not conn.get("ok"):
        await state.clear()
        return await msg.edit_text(
            f"❌ Ошибка подключения:\n<code>{esc(conn['error'])}</code>",
            parse_mode="HTML", reply_markup=cancel_kb(),
        )
    await state.clear()
    await msg.edit_text(
        f"✅ <b>Аккаунт «{esc(data['label'])}» подключён!</b>\n"
        f"👤 {esc(conn.get('name',''))} | 📱 {esc(conn.get('phone',''))}\n\n"
        f"Теперь зайдите «👤 Аккаунты → {esc(data['label'])} → 📝 Задать инструкции», чтобы "
        f"описать, как ассистент должен общаться.",
        parse_mode="HTML",
        reply_markup=main_menu_kb(ub.is_connected()),
    )


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
        await state.clear()
        await msg.edit_text(
            f"✅ <b>Аккаунт «{esc(data['label'])}» подключён!</b>\n"
            f"👤 {esc(result.get('name',''))} | 📱 {esc(result.get('phone',''))}\n\n"
            f"Теперь зайдите «👤 Аккаунты → {esc(data['label'])} → 📝 Задать инструкции», чтобы "
            f"описать, как ассистент должен общаться.",
            parse_mode="HTML",
            reply_markup=main_menu_kb(ub.is_connected()),
        )
    else:
        await msg.edit_text(
            f"❌ Ошибка:\n<code>{result['error']}</code>",
            parse_mode="HTML", reply_markup=cancel_kb(),
        )
