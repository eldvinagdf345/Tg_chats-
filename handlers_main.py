from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.filters import CommandStart
from aiogram.fsm.state import State, StatesGroup as SG

from config import ADMIN_IDS
from database import get_users_count, add_users
from keyboards import main_menu_kb, cancel_kb
import userbot as ub
import login_flow

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
#  ЗАГРУЗКА БАЗЫ КОНТАКТОВ ИЗ TXT ФАЙЛА (источник для рассылки)
# ═══════════════════════════════════════════════════════════════════════════════

class UploadStates(SG):
    waiting_file = State()


@router.callback_query(F.data == "upload_base")
async def upload_base(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return await call.answer()
    await state.set_state(UploadStates.waiting_file)
    await call.message.edit_text(
        "📥 <b>Загрузка базы</b>\n\n"
        "Отправьте <b>txt файл</b> с никнеймами — по одному на строку. Эта база "
        "используется как список контактов для рассылки.\n\n"
        "Формат:\n"
        "<code>@username1\n@username2\nusername3</code>\n\n"
        "<i>@ в начале необязателен — бот добавит сам.</i>",
        parse_mode="HTML",
        reply_markup=cancel_kb(),
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

        lines = content.splitlines()
        usernames = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            if not line.startswith("@"):
                line = "@" + line
            usernames.append(line.lower())

        if not usernames:
            await msg.edit_text("❌ Файл пуст или не содержит никнеймов.")
            return

        new_users = await add_users(usernames)
        total = await get_users_count()

        await state.clear()
        await msg.edit_text(
            f"✅ <b>База загружена</b>\n\n"
            f"В файле: {len(usernames)}\n"
            f"Новых добавлено: <b>{len(new_users)}</b>\n"
            f"Уже были в базе: {len(usernames) - len(new_users)}\n"
            f"Всего в базе: {total}",
            parse_mode="HTML",
            reply_markup=main_menu_kb(ub.is_connected()),
        )

    except Exception as e:
        await msg.edit_text(
            f"❌ Ошибка при чтении файла:\n<code>{e}</code>",
            parse_mode="HTML",
            reply_markup=cancel_kb(),
        )


@router.message(UploadStates.waiting_file)
async def upload_wrong_type(message: Message):
    await message.answer(
        "❌ Нужен именно <b>txt файл</b>. Отправьте файл, а не текст.",
        parse_mode="HTML",
    )
