from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from config import ADMIN_IDS
from database import (
    get_accounts, get_account, get_all_contacts, get_contact,
    create_contact, delete_contact, set_contact_status, set_contact_auto_send,
    get_dialogue_history, add_dialogue_message, get_message, set_message_status, set_message_text,
)
from states import DialogueSetupStates, DraftEditStates
from keyboards import (
    main_menu_kb, dialogues_list_kb, choose_account_kb, dialogue_mode_kb,
    opening_message_kb, opening_preview_kb, dialogue_detail_kb, cancel_kb,
)
import userbot as ub
import dialogue as dlg
from utils import normalize_identifier, resolve_target, esc

router = Router()


def is_admin(uid: int) -> bool:
    return uid in ADMIN_IDS


# ═══════════════════════════════════════════════════════════════════════════════
#  СПИСОК ДИАЛОГОВ
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "dialogues_menu")
async def dialogues_menu(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return await call.answer()
    await state.clear()
    contacts = await get_all_contacts()
    if not contacts:
        return await call.message.edit_text(
            "💬 <b>Диалоги</b>\n\nПока нет ни одного диалога.",
            parse_mode="HTML",
            reply_markup=dialogues_list_kb([]),
        )
    await call.message.edit_text(
        f"💬 <b>Диалоги ({len(contacts)})</b>",
        parse_mode="HTML",
        reply_markup=dialogues_list_kb(contacts),
    )


@router.callback_query(F.data.startswith("dlg_view:"))
async def dlg_view(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return await call.answer()
    contact_id = int(call.data.split(":", 1)[1])
    contact = await get_contact(contact_id)
    if not contact:
        return await call.answer("Диалог не найден", show_alert=True)

    account = await get_account(contact["account_id"])
    history = await get_dialogue_history(contact_id, limit=10)
    lines = []
    for m in history:
        prefix = "Я" if m["direction"] == "out" else "Он(а)"
        mark = " (черновик)" if m["status"] == "draft" else ""
        lines.append(f"<b>{prefix}{mark}:</b> {esc(m['text'])}")
    transcript = "\n".join(lines) if lines else "<i>переписки пока нет</i>"

    mode = "🚀 автоотправка" if contact["auto_send"] else "✍️ черновики на проверку"
    status = "🟢 активен" if contact["status"] == "active" else "⏸ на паузе"
    goal = esc(contact.get("goal")) or "—"
    who = esc(contact.get("display_name") or contact["identifier"])

    await call.message.edit_text(
        f"📇 <b>{who}</b> ({esc(contact['identifier'])})\n"
        f"👤 Аккаунт: {esc(account['label']) if account else '?'}\n"
        f"🎯 Цель: {goal}\n"
        f"Режим: {mode} | Статус: {status}\n\n"
        f"<b>Последние сообщения:</b>\n{transcript}",
        parse_mode="HTML",
        reply_markup=dialogue_detail_kb(contact),
    )


@router.callback_query(F.data.startswith("dlg_pause:"))
async def dlg_pause(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return await call.answer()
    contact_id = int(call.data.split(":", 1)[1])
    await set_contact_status(contact_id, "paused")
    await dlg_view(call)


@router.callback_query(F.data.startswith("dlg_resume:"))
async def dlg_resume(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return await call.answer()
    contact_id = int(call.data.split(":", 1)[1])
    await set_contact_status(contact_id, "active")
    await dlg_view(call)


@router.callback_query(F.data.startswith("dlg_mode_auto:"))
async def dlg_mode_auto(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return await call.answer()
    contact_id = int(call.data.split(":", 1)[1])
    await set_contact_auto_send(contact_id, True)
    await dlg_view(call)


@router.callback_query(F.data.startswith("dlg_mode_draft:"))
async def dlg_mode_draft(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return await call.answer()
    contact_id = int(call.data.split(":", 1)[1])
    await set_contact_auto_send(contact_id, False)
    await dlg_view(call)


@router.callback_query(F.data.startswith("dlg_delete:"))
async def dlg_delete(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return await call.answer()
    contact_id = int(call.data.split(":", 1)[1])
    await delete_contact(contact_id)
    await call.answer("Диалог удалён")
    await dialogues_menu(call, state)


# ═══════════════════════════════════════════════════════════════════════════════
#  НОВЫЙ ДИАЛОГ
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "dlg_new")
async def dlg_new(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return await call.answer()
    accounts = [a for a in await get_accounts() if a["connected"]]
    if not accounts:
        return await call.answer("⚠️ Сначала подключите хотя бы один аккаунт!", show_alert=True)

    if len(accounts) == 1:
        await state.update_data(account_id=accounts[0]["id"])
        await _ask_contact(call, state)
    else:
        await call.message.edit_text(
            "👤 С какого аккаунта начать диалог?",
            reply_markup=choose_account_kb(accounts),
        )


@router.callback_query(F.data.startswith("dlg_acc:"))
async def dlg_pick_account(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return await call.answer()
    account_id = int(call.data.split(":", 1)[1])
    await state.update_data(account_id=account_id)
    await _ask_contact(call, state)


async def _ask_contact(call: CallbackQuery, state: FSMContext):
    await state.set_state(DialogueSetupStates.waiting_contact)
    await call.message.edit_text(
        "📇 <b>Кому пишем?</b>\n\n"
        "Введите @username или ссылку на контакт. Можно через пробел указать имя для удобства:\n"
        "<code>@ivan_petrov Иван</code>",
        parse_mode="HTML", reply_markup=cancel_kb(),
    )


@router.message(DialogueSetupStates.waiting_contact)
async def got_contact(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    parts = message.text.strip().split(maxsplit=1)
    identifier = normalize_identifier(parts[0])
    display_name = parts[1].strip() if len(parts) > 1 else None
    await state.update_data(identifier=identifier, display_name=display_name)
    await message.answer(
        "🎯 <b>Цель диалога</b> (необязательно)\n\n"
        "Опишите, о чём и зачем должен идти разговор — ассистент будет держать это в уме "
        "при ответах. Или отправьте «-», чтобы пропустить.",
        parse_mode="HTML", reply_markup=cancel_kb(),
    )
    await state.set_state(DialogueSetupStates.waiting_goal)


@router.message(DialogueSetupStates.waiting_goal)
async def got_goal(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    raw = message.text.strip()
    goal = None if raw in ("-", "") else raw
    await state.update_data(goal=goal)
    await message.answer(
        "⚙️ <b>Режим ответов</b>\n\n"
        "«Черновики» — каждый ответ ИИ сначала присылается вам на проверку.\n"
        "«Автоматически» — ответы уходят собеседнику сразу, без подтверждения.",
        parse_mode="HTML", reply_markup=dialogue_mode_kb(),
    )


@router.callback_query(F.data.in_(["setup_mode_draft", "setup_mode_auto"]))
async def got_mode(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return await call.answer()
    await state.update_data(auto_send=(call.data == "setup_mode_auto"))
    await call.message.edit_text(
        "✉️ <b>Первое сообщение</b>\n\nКак начнём разговор?",
        parse_mode="HTML", reply_markup=opening_message_kb(),
    )


@router.callback_query(F.data == "opening_manual")
async def opening_manual(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return await call.answer()
    await state.set_state(DialogueSetupStates.waiting_opening_message)
    await call.message.edit_text(
        "✍️ Введите текст первого сообщения:",
        reply_markup=cancel_kb(),
    )


@router.callback_query(F.data == "opening_ai")
async def opening_ai(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return await call.answer()
    if not dlg.ai_available():
        return await call.answer("⚠️ ANTHROPIC_API_KEY не настроен на сервере.", show_alert=True)
    await _generate_and_preview(call, state)


@router.callback_query(F.data == "opening_ai_retry")
async def opening_ai_retry(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return await call.answer()
    await _generate_and_preview(call, state)


async def _generate_and_preview(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    draft_contact = {"goal": data.get("goal")}
    account = await get_account(data["account_id"])
    msg = await call.message.edit_text("⏳ Придумываю сообщение...")
    try:
        text = await dlg.generate_opening_message(draft_contact, account)
    except Exception as e:
        return await msg.edit_text(f"❌ Ошибка ИИ:\n<code>{e}</code>", parse_mode="HTML", reply_markup=cancel_kb())
    await state.update_data(opening_text=text)
    await msg.edit_text(
        f"🤖 <b>Черновик первого сообщения:</b>\n\n{esc(text)}",
        parse_mode="HTML", reply_markup=opening_preview_kb(),
    )


@router.callback_query(F.data == "opening_ai_send")
async def opening_ai_send(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return await call.answer()
    data = await state.get_data()
    text = data.get("opening_text")
    if not text:
        return await call.answer("Черновик не найден, попробуйте заново", show_alert=True)
    await _finalize_dialogue(call, state, text)


@router.message(DialogueSetupStates.waiting_opening_message)
async def got_opening_manual(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await _finalize_dialogue(message, state, message.text.strip())


async def _finalize_dialogue(event, state: FSMContext, opening_text: str):
    data = await state.get_data()
    account_id = data["account_id"]
    identifier = data["identifier"]

    client = ub.get_client(account_id)
    if not client:
        await state.clear()
        text = "❌ Аккаунт отключился, диалог не начат."
        if isinstance(event, CallbackQuery):
            await event.message.edit_text(text, reply_markup=main_menu_kb(ub.is_connected()))
        else:
            await event.answer(text, reply_markup=main_menu_kb(ub.is_connected()))
        return

    try:
        await client.send_message(resolve_target(identifier), opening_text)
    except Exception as e:
        err = f"❌ Не удалось отправить сообщение:\n<code>{e}</code>"
        if isinstance(event, CallbackQuery):
            await event.message.edit_text(err, parse_mode="HTML", reply_markup=cancel_kb())
        else:
            await event.answer(err, parse_mode="HTML", reply_markup=cancel_kb())
        return

    contact_id = await create_contact(
        account_id=account_id, identifier=identifier,
        display_name=data.get("display_name"), goal=data.get("goal"),
        auto_send=data.get("auto_send", False),
    )
    await add_dialogue_message(contact_id, "out", opening_text, status="sent")
    await state.clear()

    mode = "автоматическая отправка" if data.get("auto_send") else "черновики на проверку"
    confirmation = (
        f"✅ <b>Диалог начат</b>\n\n"
        f"Сообщение отправлено {esc(data.get('display_name') or identifier)}.\n"
        f"Режим ответов: {mode}."
    )
    if isinstance(event, CallbackQuery):
        await event.message.edit_text(confirmation, parse_mode="HTML", reply_markup=main_menu_kb(ub.is_connected()))
    else:
        await event.answer(confirmation, parse_mode="HTML", reply_markup=main_menu_kb(ub.is_connected()))


# ═══════════════════════════════════════════════════════════════════════════════
#  ПРОВЕРКА ЧЕРНОВИКОВ ОТВЕТОВ
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("draft_send:"))
async def draft_send(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return await call.answer()
    message_id = int(call.data.split(":", 1)[1])
    draft = await get_message(message_id)
    if not draft or draft["status"] != "draft":
        return await call.answer("Черновик уже обработан", show_alert=True)
    contact = await get_contact(draft["contact_id"])
    try:
        await dlg.send_text(contact["account_id"], contact["identifier"], draft["text"])
    except Exception as e:
        return await call.answer(f"Ошибка отправки: {e}", show_alert=True)
    await set_message_status(message_id, "sent")
    await call.message.edit_text(f"{call.message.text}\n\n✅ <b>Отправлено</b>", parse_mode="HTML")


@router.callback_query(F.data.startswith("draft_reject:"))
async def draft_reject(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return await call.answer()
    message_id = int(call.data.split(":", 1)[1])
    await set_message_status(message_id, "rejected")
    await call.message.edit_text(f"{call.message.text}\n\n❌ <b>Отклонено</b>", parse_mode="HTML")


@router.callback_query(F.data.startswith("draft_edit:"))
async def draft_edit(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return await call.answer()
    message_id = int(call.data.split(":", 1)[1])
    draft = await get_message(message_id)
    if not draft or draft["status"] != "draft":
        return await call.answer("Черновик уже обработан", show_alert=True)
    await state.update_data(edit_message_id=message_id, edit_chat_id=call.message.chat.id, edit_msg_id=call.message.message_id)
    await state.set_state(DraftEditStates.waiting_new_text)
    await call.message.reply("✏️ Пришлите новый текст ответа:")


@router.message(DraftEditStates.waiting_new_text)
async def draft_got_new_text(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    data = await state.get_data()
    message_id = data["edit_message_id"]
    new_text = message.text.strip()

    draft = await get_message(message_id)
    if not draft or draft["status"] != "draft":
        await state.clear()
        return await message.answer("⚠️ Этот черновик уже обработан.")

    contact = await get_contact(draft["contact_id"])
    try:
        await dlg.send_text(contact["account_id"], contact["identifier"], new_text)
    except Exception as e:
        await state.clear()
        return await message.answer(f"❌ Ошибка отправки:\n<code>{e}</code>", parse_mode="HTML")

    await set_message_text(message_id, new_text)
    await set_message_status(message_id, "sent")
    await state.clear()
    await message.answer("✅ Отправлено отредактированное сообщение.")

    try:
        await message.bot.edit_message_text(
            chat_id=data["edit_chat_id"], message_id=data["edit_msg_id"],
            text=f"✅ <b>Отправлено (отредактировано):</b>\n{new_text}", parse_mode="HTML",
        )
    except Exception:
        pass
