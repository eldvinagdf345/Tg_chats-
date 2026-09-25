from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from config import ADMIN_IDS
from database import (
    get_account, get_contact, update_account_profile,
    set_contact_ai_enabled, set_contact_status,
    create_template, get_templates, get_template, delete_template,
)
from states import InstructionsChatStates, QuickSettingStates, TemplateStates
from keyboards import (
    account_settings_kb, instructions_chat_kb, instructions_reset_confirm_kb, setting_edit_kb,
    templates_list_kb, template_apply_confirm_kb, cancel_kb,
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


@router.callback_query(F.data.startswith("ignore_contact:"))
async def ignore_contact(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return await call.answer()
    contact_id = int(call.data.split(":", 1)[1])
    contact = await get_contact(contact_id)
    if not contact:
        return await call.answer("Диалог не найден", show_alert=True)
    await set_contact_ai_enabled(contact_id, False)
    await set_contact_status(contact_id, "active")
    who = esc(contact.get("display_name") or contact["identifier"])
    await call.answer("Бот больше не будет отвечать этому контакту")
    await call.message.edit_text(
        f"{call.message.text}\n\n🚫 <b>Проигнорировано.</b> ИИ больше не будет отвечать "
        f"{who} — ведите диалог сами через «Диалоги».",
        parse_mode="HTML",
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
#  ШАБЛОНЫ ИНСТРУКЦИЙ
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("instr_tpl_save:"))
async def instr_tpl_save(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return await call.answer()
    account_id = int(call.data.split(":", 1)[1])
    account = await get_account(account_id)
    if not account:
        return await call.answer("Аккаунт не найден", show_alert=True)
    if not account.get("custom_instructions"):
        return await call.answer("Сначала задайте инструкции для этого аккаунта", show_alert=True)
    await state.set_state(TemplateStates.waiting_name)
    await state.update_data(tpl_account_id=account_id)
    await call.message.edit_text(
        "💾 <b>Сохранить как шаблон</b>\n\nВведите название шаблона:",
        parse_mode="HTML", reply_markup=cancel_kb(),
    )


@router.message(TemplateStates.waiting_name)
async def tpl_got_name(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    name = (message.text or "").strip()
    if not name:
        return await message.answer("Введите непустое название.")
    data = await state.get_data()
    account_id = data["tpl_account_id"]
    account = await get_account(account_id)
    await create_template(name, account.get("custom_instructions") or "")
    await state.clear()
    await message.answer(
        f"✅ Шаблон «{esc(name)}» сохранён. Теперь его можно применить к любому аккаунту.",
        parse_mode="HTML", reply_markup=instructions_chat_kb(account_id),
    )


@router.callback_query(F.data.startswith("instr_tpl_apply:"))
async def instr_tpl_apply(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return await call.answer()
    account_id = int(call.data.split(":", 1)[1])
    templates = await get_templates()
    if not templates:
        return await call.answer("Шаблонов пока нет — сначала сохраните один", show_alert=True)
    await call.message.edit_text(
        "📋 <b>Шаблоны инструкций</b>\n\n"
        "Выберите, чтобы применить к этому аккаунту (текущие инструкции будут заменены):",
        parse_mode="HTML",
        reply_markup=templates_list_kb(account_id, templates),
    )


@router.callback_query(F.data.startswith("instr_tpl_use:"))
async def instr_tpl_use(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return await call.answer()
    _, account_id, template_id = call.data.split(":")
    await call.message.edit_text(
        "⚠️ Заменить текущие инструкции этого аккаунта содержимым шаблона? "
        "Отменить будет нельзя (можно будет только задать заново).",
        reply_markup=template_apply_confirm_kb(int(account_id), int(template_id)),
    )


@router.callback_query(F.data.startswith("instr_tpl_use_yes:"))
async def instr_tpl_use_yes(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return await call.answer()
    _, account_id, template_id = call.data.split(":")
    account_id, template_id = int(account_id), int(template_id)
    tpl = await get_template(template_id)
    if not tpl:
        return await call.answer("Шаблон не найден", show_alert=True)
    await update_account_profile(account_id, custom_instructions=tpl["content"], profile_ready=1)
    await call.answer("Шаблон применён")
    await call.message.edit_text(
        f"✅ Инструкции аккаунта заменены шаблоном «{esc(tpl['name'])}».",
        parse_mode="HTML", reply_markup=instructions_chat_kb(account_id),
    )


@router.callback_query(F.data.startswith("instr_tpl_del:"))
async def instr_tpl_del(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return await call.answer()
    _, account_id, template_id = call.data.split(":")
    await delete_template(int(template_id))
    await call.answer("Шаблон удалён")
    account_id = int(account_id)
    templates = await get_templates()
    if not templates:
        return await call.message.edit_text(
            "Шаблонов больше нет.", reply_markup=instructions_chat_kb(account_id),
        )
    await call.message.edit_reply_markup(reply_markup=templates_list_kb(account_id, templates))


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
        "prompt": "Максимум ответов бота в сутки по этому аккаунту (по всем диалогам). Число, или «-» — без лимита:",
        "parser": _int_parser("max_messages_per_day"),
    },
    "work_hours": {
        "title": "Рабочие часы",
        "prompt": "Часы, когда бот может отвечать (по времени сервера), формат <code>9-22</code>. Или «-» — без ограничений:",
        "parser": _hours_parser,
    },
    "notify_chat_id": {
        "title": "Канал уведомлений",
        "prompt": (
            "Перешлите сюда любое сообщение из канала/группы, или введите его @username / "
            "числовой ID. «-» — уведомления будут приходить в этот чат:"
        ),
        "parser": None,  # обрабатывается отдельно — нужен доступ к forward_from_chat
    },
    "delay_range": {
        "title": "Задержка ответа",
        "prompt": (
            "Диапазон в секундах, например <code>30-180</code> — случайная задержка перед "
            "автоответом плюс «печатает…». «-» — по умолчанию (20-90):"
        ),
        "parser": _range_parser("delay_min_seconds", "delay_max_seconds"),
    },
    "campaign_interval": {
        "title": "Интервал рассылки",
        "prompt": (
            "Диапазон в секундах между стартом диалогов с новыми людьми при рассылке, "
            "например <code>300-900</code> (5-15 минут). «-» — по умолчанию:"
        ),
        "parser": _range_parser("campaign_interval_min_seconds", "campaign_interval_max_seconds"),
    },
    "inactivity_timeout_hours": {
        "title": "Тайм-аут неактивности",
        "prompt": (
            "Через сколько часов без ответа от собеседника переносить диалог из «Активных» "
            "в «Корзину» (переписка не теряется — просто пропадает из списка активных). "
            "Число часов, по умолчанию 24:"
        ),
        "parser": _int_parser("inactivity_timeout_hours"),
    },
}


async def _render_settings(account_id: int) -> tuple[str, dict]:
    account = await get_account(account_id)
    text = f"⚙️ <b>Настройки — {esc(account['label'])}</b>\n\nНажмите на пункт, чтобы изменить:"
    return text, account


@router.callback_query(F.data.startswith("acc_settings:"))
async def acc_settings_menu(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return await call.answer()
    account_id = int(call.data.split(":", 1)[1])
    account = await get_account(account_id)
    if not account:
        return await call.answer("Аккаунт не найден", show_alert=True)
    await state.clear()
    text, account = await _render_settings(account_id)
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=account_settings_kb(account_id, account))


@router.callback_query(F.data.startswith("set_open:"))
async def set_open(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return await call.answer()
    _, key, account_id = call.data.split(":", 2)
    account_id = int(account_id)
    setting = _SETTINGS.get(key)
    if not setting:
        return await call.answer()
    await state.set_state(QuickSettingStates.waiting_value)
    await state.update_data(setting_key=key, setting_account_id=account_id)
    await call.message.edit_text(
        f"✏️ <b>{setting['title']}</b>\n\n{setting['prompt']}",
        parse_mode="HTML", reply_markup=setting_edit_kb(account_id),
    )


@router.message(QuickSettingStates.waiting_value)
async def set_got_value(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    data = await state.get_data()
    key = data["setting_key"]
    account_id = data["setting_account_id"]
    setting = _SETTINGS[key]

    if key == "notify_chat_id":
        forwarded_chat = getattr(message, "forward_from_chat", None)
        if forwarded_chat:
            fields = {"notify_chat_id": str(forwarded_chat.id)}
        else:
            raw = (message.text or "").strip()
            fields = {"notify_chat_id": None if (not raw or raw == "-") else raw}
    else:
        raw = (message.text or "").strip()
        fields = setting["parser"](raw)
        if fields is None:
            return await message.answer(
                f"❌ Не понял формат.\n\n{setting['prompt']}", parse_mode="HTML",
            )

    await update_account_profile(account_id, **fields)
    await state.clear()
    text, account = await _render_settings(account_id)
    await message.answer(
        f"✅ Сохранено.\n\n{text}", parse_mode="HTML",
        reply_markup=account_settings_kb(account_id, account),
    )
