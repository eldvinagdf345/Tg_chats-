from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.filters import CommandStart
from aiogram.fsm.state import State, StatesGroup as SG

from config import ADMIN_IDS
from database import get_users_count, get_all_users, add_users, clear_users
from keyboards import main_menu_kb, cancel_kb, base_menu_kb, base_clear_confirm_kb
import userbot as ub
import login_flow
from utils import normalize_identifier, esc

router = Router()


def is_admin(uid: int) -> bool:
    return uid in ADMIN_IDS


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return await message.answer("⛔ Нет доступа.")
    await login_flow.cancel_login(message.from_user.id)
    await state.clear()
    await message.answer(
        "👋 <b>ИИ-помощник</b>\n\nВыберите действие:",
        parse_mode="HTML",
        reply_markup=main_menu_kb(ub.is_connected()),
    )


@router.callback_query(F.data == "back_main")
async def back_main(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return await call.answer()
    await login_flow.cancel_login(call.from_user.id)
    await state.clear()
    await call.message.edit_text(
        "👋 <b>ИИ-помощник</b>\n\nВыберите действие:",
        parse_mode="HTML",
        reply_markup=main_menu_kb(ub.is_connected()),
    )


@router.callback_query(F.data == "noop")
async def noop(call: CallbackQuery):
    await call.answer()


# ═══════════════════════════════════════════════════════════════════════════════
#  БАЗА КОНТАКТОВ (источник для рассылки)
# ═══════════════════════════════════════════════════════════════════════════════

class UploadStates(SG):
    waiting_file = State()


def _parse_username_lines(content: str) -> list[str]:
    usernames = []
    for line in content.splitlines():
        line = line.strip()
        if not line:
            continue
        usernames.append(normalize_identifier(line))
    return usernames


@router.callback_query(F.data == "base_menu")
async def base_menu(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return await call.answer()
    await state.clear()
    count = await get_users_count()
    await call.message.edit_text(
        f"👥 <b>База контактов</b>\n\nВсего в базе: {count}",
        parse_mode="HTML",
        reply_markup=base_menu_kb(count),
    )


@router.callback_query(F.data == "base_show")
async def base_show(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return await call.answer()
    count = await get_users_count()
    if count == 0:
        return await call.answer("База пуста", show_alert=True)
    users = await get_all_users()
    if count <= 100:
        await call.message.edit_text(
            f"👥 <b>В базе {count}:</b>\n\n" + "\n".join(esc(u) for u in users),
            parse_mode="HTML",
            reply_markup=base_menu_kb(count),
        )
    else:
        from aiogram.types import BufferedInputFile
        doc = BufferedInputFile("\n".join(users).encode(), filename=f"baza_{count}.txt")
        await call.message.answer_document(doc, caption=f"👥 Всего в базе: {count}")
        await call.message.edit_reply_markup(reply_markup=base_menu_kb(count))


@router.callback_query(F.data == "base_add")
async def base_add(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return await call.answer()
    await state.set_state(UploadStates.waiting_file)
    await call.message.edit_text(
        "➕ <b>Добавление контактов</b>\n\n"
        "Отправьте <b>txt файл</b>, или просто пришлите текстом — по одному нику/ссылке "
        "на строку:\n\n"
        "<code>@username1\nhttps://t.me/username2\nusername3</code>\n\n"
        "<i>@ в начале необязателен — бот добавит сам.</i>",
        parse_mode="HTML",
        reply_markup=cancel_kb(),
    )


async def _add_usernames_and_report(usernames: list[str], msg: Message, source_label: str):
    if not usernames:
        await msg.edit_text(f"❌ {source_label} пуст(о) или не содержит никнеймов.")
        return
    new_users = await add_users(usernames)
    total = await get_users_count()
    await msg.edit_text(
        f"✅ <b>База обновлена</b>\n\n"
        f"Получено: {len(usernames)}\n"
        f"Новых добавлено: <b>{len(new_users)}</b>\n"
        f"Уже были в базе: {len(usernames) - len(new_users)}\n"
        f"Всего в базе: {total}",
        parse_mode="HTML",
        reply_markup=base_menu_kb(total),
    )


@router.message(UploadStates.waiting_file, F.document)
async def got_base_file(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return

    doc = message.document
    if not doc.file_name.endswith(".txt"):
        return await message.answer("❌ Нужен файл формата <b>.txt</b>", parse_mode="HTML")

    msg = await message.answer("⏳ Читаю файл...")
    try:
        file = await message.bot.get_file(doc.file_id)
        downloaded = await message.bot.download_file(file.file_path)
        content = downloaded.read().decode("utf-8", errors="ignore")
        usernames = _parse_username_lines(content)
        await state.clear()
        await _add_usernames_and_report(usernames, msg, "Файл")
    except Exception as e:
        await msg.edit_text(
            f"❌ Ошибка при чтении файла:\n<code>{e}</code>",
            parse_mode="HTML",
            reply_markup=cancel_kb(),
        )


@router.message(UploadStates.waiting_file, F.text)
async def got_base_text(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    msg = await message.answer("⏳ Обрабатываю...")
    usernames = _parse_username_lines(message.text)
    await state.clear()
    await _add_usernames_and_report(usernames, msg, "Сообщение")


@router.message(UploadStates.waiting_file)
async def upload_wrong_type(message: Message):
    await message.answer(
        "❌ Отправьте <b>txt файл</b> или текст с никами/ссылками, по одному на строку.",
        parse_mode="HTML",
    )


@router.callback_query(F.data == "base_clear")
async def base_clear(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return await call.answer()
    count = await get_users_count()
    if count == 0:
        return await call.answer("База уже пуста", show_alert=True)
    await call.message.edit_text(
        f"⚠️ Очистить базу контактов ({count} шт.)? Действие необратимо.",
        reply_markup=base_clear_confirm_kb(),
    )


@router.callback_query(F.data == "base_clear_yes")
async def base_clear_yes(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return await call.answer()
    await clear_users()
    await call.answer("База очищена")
    await call.message.edit_text(
        "👥 <b>База контактов</b>\n\nВсего в базе: 0",
        parse_mode="HTML",
        reply_markup=base_menu_kb(0),
    )
