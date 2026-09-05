from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def main_menu_kb(has_accounts: bool) -> InlineKeyboardMarkup:
    accounts_text = "👤 Аккаунты" + (" ✅" if has_accounts else " (не подключены)")
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=accounts_text, callback_data="accounts_menu")],
        [InlineKeyboardButton(text="💬 Диалоги", callback_data="dialogues_menu")],
        [InlineKeyboardButton(text="🚀 Начать парсинг", callback_data="start_parsing")],
        [InlineKeyboardButton(text="📋 Результаты парсинга", callback_data="show_results")],
        [InlineKeyboardButton(text="📥 Загрузить базу", callback_data="upload_base")],
    ])


def channel_select_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Выбрать из моих каналов", callback_data="channel_from_list")],
        [InlineKeyboardButton(text="🔗 Ввести ссылку", callback_data="channel_by_link")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_main")],
    ])


def channels_list_kb(channels: list) -> InlineKeyboardMarkup:
    buttons = []
    for title, cid in channels:
        short = title[:30] + "…" if len(title) > 30 else title
        buttons.append([InlineKeyboardButton(text=short, callback_data=f"pick_channel:{cid}")])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="start_parsing")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def topics_list_kb(topics: list, channel: str) -> InlineKeyboardMarkup:
    buttons = []
    for tid, title in topics:
        short = title[:30] + "…" if len(title) > 30 else title
        buttons.append([InlineKeyboardButton(text=f"💬 {short}", callback_data=f"pick_topic:{tid}")])
    buttons.append([InlineKeyboardButton(text="📥 Все темы сразу", callback_data="pick_topic:all")])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="start_parsing")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def parse_mode_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📥 Все посты", callback_data="mode_all")],
        [InlineKeyboardButton(text="🔢 Указать количество постов", callback_data="mode_count")],
        [InlineKeyboardButton(text="📅 Указать диапазон дат", callback_data="mode_dates")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_main")],
    ])


def confirm_parse_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="▶️ Запустить", callback_data="run_parser")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_main")],
    ])


def running_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏳ В работе...", callback_data="noop")],
    ])


def done_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Завершено", callback_data="noop")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_main")],
    ])


def cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="back_main")],
    ])


# ── accounts ──────────────────────────────────────────────────────────────────

def accounts_list_kb(accounts: list[dict]) -> InlineKeyboardMarkup:
    buttons = []
    for acc in accounts:
        status = "🟢" if acc["connected"] else "🔴"
        buttons.append([InlineKeyboardButton(
            text=f"{status} {acc['label']} ({acc['phone']})",
            callback_data=f"acc_view:{acc['id']}",
        )])
    buttons.append([InlineKeyboardButton(text="➕ Добавить аккаунт", callback_data="acc_add")])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="back_main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def account_detail_kb(account_id: int, connected: bool) -> InlineKeyboardMarkup:
    toggle = (
        InlineKeyboardButton(text="🔌 Отключить", callback_data=f"acc_disconnect:{account_id}")
        if connected else
        InlineKeyboardButton(text="🔄 Переподключить", callback_data=f"acc_reconnect:{account_id}")
    )
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎭 Профиль общения", callback_data=f"acc_profile:{account_id}")],
        [toggle],
        [InlineKeyboardButton(text="🗑 Удалить аккаунт", callback_data=f"acc_delete:{account_id}")],
        [InlineKeyboardButton(text="◀️ К списку", callback_data="accounts_menu")],
    ])


# ── communication-profile wizard ────────────────────────────────────────────

def profile_address_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="На «ты»", callback_data="prof_addr:ty")],
        [InlineKeyboardButton(text="На «вы»", callback_data="prof_addr:vy")],
    ])


def profile_tone_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="😊 Неформальный, дружеский", callback_data="prof_tone:friendly")],
        [InlineKeyboardButton(text="😐 Нейтральный", callback_data="prof_tone:neutral")],
        [InlineKeyboardButton(text="💼 Деловой", callback_data="prof_tone:business")],
    ])


def profile_length_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✂️ Короткие (1 фраза)", callback_data="prof_len:short")],
        [InlineKeyboardButton(text="📝 Средние (2-3 фразы)", callback_data="prof_len:medium")],
        [InlineKeyboardButton(text="📄 Развёрнутые", callback_data="prof_len:long")],
    ])


def profile_emoji_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚫 Никогда", callback_data="prof_emoji:none")],
        [InlineKeyboardButton(text="🙂 Изредка", callback_data="prof_emoji:sometimes")],
        [InlineKeyboardButton(text="😄 Часто", callback_data="prof_emoji:often")],
    ])


def profile_literacy_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Грамотно, аккуратно", callback_data="prof_lit:careful")],
        [InlineKeyboardButton(text="💬 Как в обычной переписке", callback_data="prof_lit:casual")],
    ])


def profile_fallback_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="↪️ Перевести тему", callback_data="prof_fb:deflect")],
        [InlineKeyboardButton(text="⏰ Сказать «отвечу позже»", callback_data="prof_fb:later")],
        [InlineKeyboardButton(text="🔔 Сразу звать меня", callback_data="prof_fb:escalate")],
    ])


def account_delete_confirm_kb(account_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚠️ Да, удалить безвозвратно", callback_data=f"acc_delete_yes:{account_id}")],
        [InlineKeyboardButton(text="◀️ Отмена", callback_data=f"acc_view:{account_id}")],
    ])


# ── dialogues ─────────────────────────────────────────────────────────────────

def dialogues_list_kb(contacts: list[dict]) -> InlineKeyboardMarkup:
    buttons = []
    for c in contacts:
        mark = "🟢" if c["status"] == "active" else "⏸"
        name = c.get("display_name") or c["identifier"]
        buttons.append([InlineKeyboardButton(text=f"{mark} {name}", callback_data=f"dlg_view:{c['id']}")])
    buttons.append([InlineKeyboardButton(text="➕ Новый диалог", callback_data="dlg_new")])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="back_main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def choose_account_kb(accounts: list[dict]) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text=f"{a['label']} ({a['phone']})", callback_data=f"dlg_acc:{a['id']}")]
        for a in accounts
    ]
    buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="back_main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def dialogue_mode_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✍️ Черновики (проверять перед отправкой)", callback_data="setup_mode_draft")],
        [InlineKeyboardButton(text="🚀 Отправлять автоматически", callback_data="setup_mode_auto")],
    ])


def opening_message_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🤖 Пусть ИИ придумает", callback_data="opening_ai")],
        [InlineKeyboardButton(text="✍️ Напишу сам(а)", callback_data="opening_manual")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="back_main")],
    ])


def opening_preview_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Отправить", callback_data="opening_ai_send")],
        [InlineKeyboardButton(text="🔄 Другой вариант", callback_data="opening_ai_retry")],
        [InlineKeyboardButton(text="✍️ Написать самому", callback_data="opening_manual")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="back_main")],
    ])


def dialogue_detail_kb(contact: dict) -> InlineKeyboardMarkup:
    pause_btn = (
        InlineKeyboardButton(text="▶️ Возобновить", callback_data=f"dlg_resume:{contact['id']}")
        if contact["status"] != "active" else
        InlineKeyboardButton(text="⏸ Приостановить", callback_data=f"dlg_pause:{contact['id']}")
    )
    mode_btn = (
        InlineKeyboardButton(text="✍️ Включить проверку черновиков", callback_data=f"dlg_mode_draft:{contact['id']}")
        if contact["auto_send"] else
        InlineKeyboardButton(text="🚀 Включить автоотправку", callback_data=f"dlg_mode_auto:{contact['id']}")
    )
    return InlineKeyboardMarkup(inline_keyboard=[
        [pause_btn],
        [mode_btn],
        [InlineKeyboardButton(text="🗑 Удалить диалог", callback_data=f"dlg_delete:{contact['id']}")],
        [InlineKeyboardButton(text="◀️ К списку", callback_data="dialogues_menu")],
    ])


def draft_approval_kb(message_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Отправить", callback_data=f"draft_send:{message_id}"),
            InlineKeyboardButton(text="✏️ Изменить", callback_data=f"draft_edit:{message_id}"),
        ],
        [InlineKeyboardButton(text="❌ Отклонить", callback_data=f"draft_reject:{message_id}")],
    ])
