from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def main_menu_kb(is_connected: bool) -> InlineKeyboardMarkup:
    connect_text = "✅ Аккаунт подключён" if is_connected else "🔗 Подключить аккаунт"
def main_menu_kb(has_accounts: bool) -> InlineKeyboardMarkup:
    accounts_text = "👤 Аккаунты" + (" ✅" if has_accounts else " (не подключены)")
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=connect_text, callback_data="connect_account")],
        [InlineKeyboardButton(text="🚀 Начать парсинг", callback_data="start_parsing")],
        [InlineKeyboardButton(text="📋 Результаты парсинга", callback_data="show_results")],
        [InlineKeyboardButton(text=accounts_text, callback_data="accounts_menu")],
        [InlineKeyboardButton(text="💬 Диалоги", callback_data="dialogues_menu")],
        [InlineKeyboardButton(text="📨 Рассылка", callback_data="campaign_menu")],
        [InlineKeyboardButton(text="📥 Загрузить базу", callback_data="upload_base")],
    ])


def channel_select_kb() -> InlineKeyboardMarkup:
def auth_method_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Выбрать из моих каналов", callback_data="channel_from_list")],
        [InlineKeyboardButton(text="🔗 Ввести ссылку", callback_data="channel_by_link")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_main")],
        [InlineKeyboardButton(text="📱 Войти по номеру телефона", callback_data="auth_phone")],
        [InlineKeyboardButton(text="✍️ У меня есть Session String", callback_data="auth_session_string")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="back_main")],
    ])


def cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="back_main")],
    ])


def channels_list_kb(channels: list) -> InlineKeyboardMarkup:
# ── accounts ──────────────────────────────────────────────────────────────────

def accounts_list_kb(accounts: list[dict]) -> InlineKeyboardMarkup:
    buttons = []
    for title, cid in channels:
        short = title[:30] + "…" if len(title) > 30 else title
        buttons.append([InlineKeyboardButton(text=short, callback_data=f"pick_channel:{cid}")])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="start_parsing")])
    for acc in accounts:
        status = "🟢" if acc["connected"] else "🔴"
        buttons.append([InlineKeyboardButton(
            text=f"{status} {acc['label']} ({acc['phone']})",
            callback_data=f"acc_view:{acc['id']}",
        )])
    buttons.append([InlineKeyboardButton(text="➕ Добавить аккаунт", callback_data="acc_add")])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="back_main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def topics_list_kb(topics: list, channel: str) -> InlineKeyboardMarkup:
def account_detail_kb(account_id: int, connected: bool) -> InlineKeyboardMarkup:
    toggle = (
        InlineKeyboardButton(text="🔌 Отключить", callback_data=f"acc_disconnect:{account_id}")
        if connected else
        InlineKeyboardButton(text="🔄 Переподключить", callback_data=f"acc_reconnect:{account_id}")
    )
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Задать инструкции", callback_data=f"instr_open:{account_id}")],
        [InlineKeyboardButton(text="⚙️ Настройки", callback_data=f"acc_settings:{account_id}")],
        [toggle],
        [InlineKeyboardButton(text="🗑 Удалить аккаунт", callback_data=f"acc_delete:{account_id}")],
        [InlineKeyboardButton(text="◀️ К списку", callback_data="accounts_menu")],
    ])


# ── свободный чат инструкций ─────────────────────────────────────────────────

def instructions_chat_kb(account_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📄 Показать текущий документ", callback_data=f"instr_show:{account_id}")],
        [InlineKeyboardButton(text="🗑 Сбросить инструкции", callback_data=f"instr_reset:{account_id}")],
        [InlineKeyboardButton(text="✅ Готово", callback_data=f"acc_view:{account_id}")],
    ])


def instructions_reset_confirm_kb(account_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚠️ Да, стереть всё", callback_data=f"instr_reset_yes:{account_id}")],
        [InlineKeyboardButton(text="◀️ Отмена", callback_data=f"instr_open:{account_id}")],
    ])


# ── настройки аккаунта (жёсткие правила / тайминг / уведомления) ────────────

def account_settings_kb(account_id: int, account: dict) -> InlineKeyboardMarkup:
    def line(label, key):
        return [InlineKeyboardButton(text=label, callback_data=f"set_open:{key}:{account_id}")]

    return InlineKeyboardMarkup(inline_keyboard=[
        line(f"🚫 Стоп-слова: {account.get('stop_keywords') or '—'}", "stop_keywords"),
        line(f"🔢 Лимит за диалог: {account.get('max_messages_per_dialogue') or '—'}", "max_messages_per_dialogue"),
        line(f"📅 Лимит за сутки: {account.get('max_messages_per_day') or '—'}", "max_messages_per_day"),
        line(
            f"🕐 Рабочие часы: {_hours_label(account)}",
            "work_hours",
        ),
        line(f"🔔 Канал уведомлений: {account.get('notify_chat_id') or 'этот чат'}", "notify_chat_id"),
        line(
            f"⏱ Задержка ответа: {account.get('delay_min_seconds', 20)}-{account.get('delay_max_seconds', 90)} сек",
            "delay_range",
        ),
        line(
            f"📨 Интервал рассылки: {account.get('campaign_interval_min_seconds', 300)}-"
            f"{account.get('campaign_interval_max_seconds', 900)} сек",
            "campaign_interval",
        ),
        [InlineKeyboardButton(text="◀️ Назад", callback_data=f"acc_view:{account_id}")],
    ])


def _hours_label(account: dict) -> str:
    start, end = account.get("work_hours_start"), account.get("work_hours_end")
    return f"{start}:00–{end}:00" if start is not None and end is not None else "без ограничений"


def setting_edit_kb(account_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data=f"acc_settings:{account_id}")],
    ])


def account_delete_confirm_kb(account_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚠️ Да, удалить безвозвратно", callback_data=f"acc_delete_yes:{account_id}")],
        [InlineKeyboardButton(text="◀️ Отмена", callback_data=f"acc_view:{account_id}")],
    ])


# ── dialogues ─────────────────────────────────────────────────────────────────

def dialogues_list_kb(contacts: list[dict]) -> InlineKeyboardMarkup:
    buttons = []
    for tid, title in topics:
        short = title[:30] + "…" if len(title) > 30 else title
        buttons.append([InlineKeyboardButton(text=f"💬 {short}", callback_data=f"pick_topic:{tid}")])
    buttons.append([InlineKeyboardButton(text="📥 Все темы сразу", callback_data="pick_topic:all")])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="start_parsing")])
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


def parse_mode_kb() -> InlineKeyboardMarkup:
def dialogue_mode_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📥 Все посты", callback_data="mode_all")],
        [InlineKeyboardButton(text="🔢 Указать количество постов", callback_data="mode_count")],
        [InlineKeyboardButton(text="📅 Указать диапазон дат", callback_data="mode_dates")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_main")],
        [InlineKeyboardButton(text="✍️ Черновики (проверять перед отправкой)", callback_data="setup_mode_draft")],
        [InlineKeyboardButton(text="🚀 Отправлять автоматически", callback_data="setup_mode_auto")],
    ])


def confirm_parse_kb() -> InlineKeyboardMarkup:
def opening_message_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="▶️ Запустить", callback_data="run_parser")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_main")],
        [InlineKeyboardButton(text="🤖 Пусть ИИ придумает", callback_data="opening_ai")],
        [InlineKeyboardButton(text="✍️ Напишу сам(а)", callback_data="opening_manual")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="back_main")],
    ])


def running_kb() -> InlineKeyboardMarkup:
def opening_preview_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏳ В работе...", callback_data="noop")],
        [InlineKeyboardButton(text="✅ Отправить", callback_data="opening_ai_send")],
        [InlineKeyboardButton(text="🔄 Другой вариант", callback_data="opening_ai_retry")],
        [InlineKeyboardButton(text="✍️ Написать самому", callback_data="opening_manual")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="back_main")],
    ])


def done_kb() -> InlineKeyboardMarkup:
def dialogue_detail_kb(contact: dict) -> InlineKeyboardMarkup:
    pause_btn = (
        InlineKeyboardButton(text="▶️ Возобновить", callback_data=f"dlg_resume:{contact['id']}")
