from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def main_menu_kb(has_accounts: bool) -> InlineKeyboardMarkup:
    accounts_text = "👤 Аккаунты" + (" ✅" if has_accounts else " (не подключены)")
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=accounts_text, callback_data="accounts_menu")],
        [InlineKeyboardButton(text="💬 Диалоги", callback_data="dialogues_menu")],
        [InlineKeyboardButton(text="📨 Рассылка", callback_data="campaign_menu")],
        [InlineKeyboardButton(text="👥 База контактов", callback_data="base_menu")],
    ])


def base_menu_kb(count: int) -> InlineKeyboardMarkup:
    buttons = []
    if count > 0:
        buttons.append([InlineKeyboardButton(text="👁 Показать базу", callback_data="base_show")])
    buttons.append([InlineKeyboardButton(text="➕ Добавить контакты", callback_data="base_add")])
    if count > 0:
        buttons.append([InlineKeyboardButton(text="🧹 Очистить базу", callback_data="base_clear")])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="back_main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def base_clear_confirm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚠️ Да, очистить", callback_data="base_clear_yes")],
        [InlineKeyboardButton(text="◀️ Отмена", callback_data="base_menu")],
    ])


def auth_method_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📱 Войти по номеру телефона", callback_data="auth_phone")],
        [InlineKeyboardButton(text="✍️ У меня есть Session String", callback_data="auth_session_string")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="back_main")],
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
    for c in contacts:
        mark = "🟢" if c["status"] == "active" else "⏸"
        name = c.get("display_name") or c["identifier"]
        buttons.append([InlineKeyboardButton(text=f"{mark} {name}", callback_data=f"dlg_view:{c['id']}")])
    buttons.append([InlineKeyboardButton(text="➕ Новый диалог", callback_data="dlg_new")])
    if contacts:
        buttons.append([InlineKeyboardButton(text="🗑 Аннулировать...", callback_data="dlg_bulk_start")])
        buttons.append([InlineKeyboardButton(text="🗑 Аннулировать все", callback_data="dlg_bulk_all")])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="back_main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def dialogues_select_kb(contacts: list[dict], selected_ids: set[int]) -> InlineKeyboardMarkup:
    buttons = []
    for c in contacts:
        mark = "✅" if c["id"] in selected_ids else "⬜"
        name = c.get("display_name") or c["identifier"]
        buttons.append([InlineKeyboardButton(text=f"{mark} {name}", callback_data=f"dlg_bulk_toggle:{c['id']}")])
    buttons.append([InlineKeyboardButton(
        text=f"🗑 Аннулировать выбранные ({len(selected_ids)})",
        callback_data="dlg_bulk_confirm",
    )])
    buttons.append([InlineKeyboardButton(text="◀️ Отмена", callback_data="dialogues_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def dialogues_bulk_all_confirm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚠️ Да, аннулировать все", callback_data="dlg_bulk_all_yes")],
        [InlineKeyboardButton(text="◀️ Отмена", callback_data="dialogues_menu")],
    ])


def choose_account_kb(accounts: list[dict]) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text=f"{a['label']} ({a['phone']})", callback_data=f"dlg_acc:{a['id']}")]
        for a in accounts
    ]
    buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="back_main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


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
    rows = [[pause_btn], [mode_btn]]
    if not contact["ai_enabled"]:
        rows.append([InlineKeyboardButton(text="🤖 Включить ИИ снова", callback_data=f"dlg_ai_on:{contact['id']}")])
    rows.append([InlineKeyboardButton(text="🗑 Удалить диалог", callback_data=f"dlg_delete:{contact['id']}")])
    rows.append([InlineKeyboardButton(text="◀️ К списку", callback_data="dialogues_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def stop_action_kb(contact_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Указать дальнейшие действия", callback_data=f"fix_pattern:{contact_id}")],
        [InlineKeyboardButton(text="🚫 Игнорировать", callback_data=f"ignore_contact:{contact_id}")],
    ])


def draft_approval_kb(message_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Отправить", callback_data=f"draft_send:{message_id}"),
            InlineKeyboardButton(text="✏️ Изменить", callback_data=f"draft_edit:{message_id}"),
        ],
        [InlineKeyboardButton(text="❌ Отклонить", callback_data=f"draft_reject:{message_id}")],
    ])


# ── рассылка ──────────────────────────────────────────────────────────────────

def campaign_choose_account_kb(accounts: list[dict]) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text=f"{a['label']} ({a['phone']})", callback_data=f"camp_acc:{a['id']}")]
        for a in accounts
    ]
    buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="back_main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def campaign_confirm_kb(account_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="▶️ Запустить рассылку", callback_data=f"campaign_start:{account_id}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="back_main")],
    ])


def campaign_running_kb(account_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏸ Остановить рассылку", callback_data=f"campaign_stop:{account_id}")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_main")],
    ])
