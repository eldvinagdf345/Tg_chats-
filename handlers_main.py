

@router.callback_query(F.data == "channel_by_link")
async def channel_by_link(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return await call.answer()
    await state.set_state(ParserStates.waiting_channel_link)
    await call.message.edit_text(
        "🔗 <b>Ввод ссылки</b>\n\nВведите ссылку или @username канала:",
        parse_mode="HTML", reply_markup=cancel_kb(),
    )


@router.message(ParserStates.waiting_channel_link)
async def got_channel_link(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return

    class FakeCall:
        def __init__(self, msg):
            self.message = msg
        async def answer(self):
            pass

    await state.update_data(channel=message.text.strip())
    fake = FakeCall(message)
    # Send a new message to act as the editable message
    sent = await message.answer("⏳")
    fake.message = sent
    await _after_channel_selected(fake, state, message.text.strip())


# ── Выбор темы форума ─────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("pick_topic:"))
async def pick_topic(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return await call.answer()
    topic_raw = call.data.split(":", 1)[1]
    if topic_raw == "all":
        await state.update_data(topic_id=None)
    else:
        await state.update_data(topic_id=int(topic_raw))
    await state.set_state(ParserStates.waiting_mode_choice)
    data = await state.get_data()
    topic_label = "Все темы" if topic_raw == "all" else f"Тема #{topic_raw}"
    await call.message.edit_text(
        f"📡 Канал: <code>{data['channel']}</code>\n"
        f"💬 {topic_label}\n\nВыберите режим парсинга:",
        parse_mode="HTML",
        reply_markup=parse_mode_kb(),
    )


# ── Режим парсинга ────────────────────────────────────────────────────────────

@router.callback_query(F.data == "mode_all")
async def mode_all(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return await call.answer()
    await state.update_data(mode="all", count_value=None)
    data = await state.get_data()
    await state.set_state(ParserStates.confirming)
    await call.message.edit_text(
        f"✅ Канал: <code>{data['channel']}</code>\n"
        f"📌 Режим: все посты\n\nНажмите «Запустить»:",
        parse_mode="HTML", reply_markup=confirm_parse_kb(),
    )


@router.callback_query(F.data == "mode_count")
async def mode_count(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return await call.answer()
    await state.set_state(ParserStates.waiting_count)
    await call.message.edit_text(
        "🔢 <b>Количество постов</b>\n\n"
        "• <code>10</code> — последние 10 постов\n"
        "• <code>-10, 5</code> — пропустить 10 свежих, парсить следующие 5",
        parse_mode="HTML", reply_markup=cancel_kb(),
    )


@router.message(ParserStates.waiting_count)
async def got_count(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    value = message.text.strip()
    try:
        if "," in value:
            parts = value.split(",")
            skip = int(parts[0].strip())
            take = int(parts[1].strip())
            assert take > 0
            summary = f"Пропустить {abs(skip)} → парсить {take}"
        else:
            n = int(value)
            assert n > 0
            summary = f"Последние {n} постов"
    except Exception:
        return await message.answer(
            "❌ Неверный формат. Пример: <code>10</code> или <code>-10, 5</code>",
            parse_mode="HTML",
        )
    await state.update_data(mode="count", count_value=value)
    data = await state.get_data()
    await state.set_state(ParserStates.confirming)
    await message.answer(
        f"✅ Канал: <code>{data['channel']}</code>\n📌 {summary}\n\nНажмите «Запустить»:",
        parse_mode="HTML", reply_markup=confirm_parse_kb(),
    )


@router.callback_query(F.data == "mode_dates")
async def mode_dates(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return await call.answer()
    await state.set_state(ParserStates.waiting_date_from)
    await call.message.edit_text(
        "📅 Введите дату начала (<code>ДД.ММ.ГГГГ</code>):",
        parse_mode="HTML", reply_markup=cancel_kb(),
    )


@router.message(ParserStates.waiting_date_from)
async def got_date_from(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    try:
        dt = datetime.strptime(message.text.strip(), "%d.%m.%Y")
    except ValueError:
        return await message.answer("❌ Формат: <code>ДД.ММ.ГГГГ</code>", parse_mode="HTML")
    await state.update_data(date_from=dt.isoformat())
    await state.set_state(ParserStates.waiting_date_to)
    await message.answer("📅 Введите дату конца (<code>ДД.ММ.ГГГГ</code>):",
                         parse_mode="HTML", reply_markup=cancel_kb())


@router.message(ParserStates.waiting_date_to)
async def got_date_to(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    try:
        dt_to = datetime.strptime(message.text.strip(), "%d.%m.%Y")
    except ValueError:
        return await message.answer("❌ Формат: <code>ДД.ММ.ГГГГ</code>", parse_mode="HTML")
    await state.update_data(mode="dates", date_to=dt_to.isoformat())
    data = await state.get_data()
    d_from = datetime.fromisoformat(data["date_from"]).strftime("%d.%m.%Y")
    await state.set_state(ParserStates.confirming)
    await message.answer(
        f"✅ Канал: <code>{data['channel']}</code>\n"
        f"📅 {d_from} — {dt_to.strftime('%d.%m.%Y')}\n\nНажмите «Запустить»:",
        parse_mode="HTML", reply_markup=confirm_parse_kb(),
    )


# ═══════════════════════════════════════════════════════════════════════════════
#  ЗАПУСК
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "run_parser")
async def run_parser(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return await call.answer()
    data = await state.get_data()
    await state.clear()

    channel     = data.get("channel", "")
    mode        = data.get("mode", "all")
    count_value = data.get("count_value")
    topic_id    = data.get("topic_id")
    date_from   = datetime.fromisoformat(data["date_from"]) if data.get("date_from") else None
    date_to     = datetime.fromisoformat(data["date_to"])   if data.get("date_to")   else None

    status_msg = await call.message.edit_text(
        "⏳ <b>Парсер запущен...</b>", parse_mode="HTML", reply_markup=running_kb()
    )

    try:
        async def progress(info):
            if isinstance(info, str) and info.startswith("post_"):
                cur, total = info.split("_")[1].split("/")
                try:
                    await status_msg.edit_text(
                        f"⏳ <b>В работе...</b>\n\n📄 Пост {cur} из {total}",
                        parse_mode="HTML", reply_markup=running_kb(),
                    )
                except Exception:
                    pass

        raw = await parse_channel(
            channel=channel, mode=mode, count_value=count_value,
            date_from=date_from, date_to=date_to,
            topic_id=topic_id,
            progress_callback=progress,
        )
        new_users = await add_users(raw)
        total_db  = await get_users_count()

        if not new_users:
            text = (f"✅ <b>Завершено</b>\n\nНайдено: {len(raw)} | Новых: <b>0</b> | В базе: {total_db}\n\nВсе уже в базе.")
        else:
            preview = "\n".join(new_users[:100])
            suffix  = f"\n…ещё {len(new_users)-100}" if len(new_users) > 100 else ""
            text = (f"✅ <b>Завершено</b>\n\nНайдено: {len(raw)} | Новых: <b>{len(new_users)}</b> | В базе: {total_db}\n\n{preview}{suffix}")

        await status_msg.edit_text(text, parse_mode="HTML", reply_markup=done_kb())

        if len(new_users) > 100:
            doc = BufferedInputFile("\n".join(new_users).encode(), filename=f"new_{len(new_users)}.txt")
            await call.message.answer_document(doc, caption=f"📄 Полный список ({len(new_users)} шт.)")

    except Exception as e:
        await status_msg.edit_text(
            f"❌ <b>Ошибка:</b>\n<code>{e}</code>",
            parse_mode="HTML", reply_markup=done_kb(),
        )


# ═══════════════════════════════════════════════════════════════════════════════
#  ЗАГРУЗКА БАЗЫ ИЗ TXT ФАЙЛА
# ═══════════════════════════════════════════════════════════════════════════════

from aiogram.fsm.state import State, StatesGroup as SG

class UploadStates(SG):
    waiting_file = State()

    await state.set_state(UploadStates.waiting_file)
    await call.message.edit_text(
        "📥 <b>Загрузка базы</b>\n\n"
        "Отправьте <b>txt файл</b> с никнеймами — по одному на строку.\n\n"
        "Отправьте <b>txt файл</b> с никнеймами — по одному на строку. Эта база "
        "используется как список контактов для рассылки.\n\n"
        "Формат:\n"
        "<code>@username1\n@username2\nusername3</code>\n\n"
        "<i>@ в начале необязателен — бот добавит сам.</i>",
    msg = await message.answer("⏳ Читаю файл...")

    try:
        # Download file bytes
        file = await message.bot.get_file(doc.file_id)
        downloaded = await message.bot.download_file(file.file_path)
        content = downloaded.read().decode("utf-8", errors="ignore")

        # Parse usernames
        lines = content.splitlines()
        usernames = []
        for line in lines:
            await msg.edit_text("❌ Файл пуст или не содержит никнеймов.")
            return

        # Add to DB
        from database import add_users
        new_users = await add_users(usernames)
        total = await get_users_count()

