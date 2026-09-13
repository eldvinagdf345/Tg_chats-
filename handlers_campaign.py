from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from config import ADMIN_IDS
from database import get_accounts, get_account, get_all_users, get_users_count
from states import CampaignStates
from keyboards import (
    main_menu_kb, campaign_choose_account_kb, campaign_mode_kb, campaign_confirm_kb,
    campaign_running_kb, cancel_kb,
)
import campaign

router = Router()


def is_admin(uid: int) -> bool:
    return uid in ADMIN_IDS


@router.callback_query(F.data == "campaign_menu")
async def campaign_menu(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return await call.answer()
    await state.clear()
    accounts = [a for a in await get_accounts() if a["connected"]]
    if not accounts:
        return await call.answer("⚠️ Сначала подключите хотя бы один аккаунт!", show_alert=True)

    count = await get_users_count()
    if count == 0:
        return await call.answer(
            "⚠️ База пуста — сначала запустите парсинг или загрузите базу («📥 Загрузить базу»).",
            show_alert=True,
        )

    if len(accounts) == 1:
        await state.update_data(campaign_account_id=accounts[0]["id"])
        await _ask_goal(call, state, count)
    else:
        await call.message.edit_text(
            f"📨 <b>Рассылка</b>\n\nВ базе {count} контактов. С какого аккаунта начнём?",
            parse_mode="HTML", reply_markup=campaign_choose_account_kb(accounts),
        )


@router.callback_query(F.data.startswith("camp_acc:"))
async def campaign_pick_account(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return await call.answer()
    account_id = int(call.data.split(":", 1)[1])
    await state.update_data(campaign_account_id=account_id)
    count = await get_users_count()
    await _ask_goal(call, state, count)


async def _ask_goal(call: CallbackQuery, state: FSMContext, count: int):
    data = await state.get_data()
    account_id = data["campaign_account_id"]
    if campaign.is_running(account_id):
        return await call.message.edit_text(
            "⚠️ У этого аккаунта уже идёт рассылка.",
            reply_markup=campaign_running_kb(account_id),
        )
    await state.set_state(CampaignStates.waiting_goal)
    await call.message.edit_text(
        f"🎯 <b>Цель рассылки</b> (необязательно)\n\n"
        f"В базе {count} контактов. Опишите, о чём и зачем писать — ассистент придумает своё "
        f"приветствие каждому, держа это в уме. Или «-», чтобы просто поздороваться:",
        parse_mode="HTML", reply_markup=cancel_kb(),
    )


@router.message(CampaignStates.waiting_goal)
async def campaign_got_goal(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    raw = message.text.strip()
    goal = None if raw in ("-", "") else raw
    await state.update_data(goal=goal)
    await state.set_state(CampaignStates.waiting_mode)
    await message.answer(
        "⚙️ <b>Режим ответов на сообщения людей из рассылки</b>\n\n"
        "«Черновики» — каждый ответ ИИ сначала присылается вам на проверку.\n"
        "«Автоматически» — ответы уходят сразу, без подтверждения.",
        parse_mode="HTML", reply_markup=campaign_mode_kb(),
    )


@router.callback_query(CampaignStates.waiting_mode, F.data.in_(["campaign_mode_draft", "campaign_mode_auto"]))
async def campaign_got_mode(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return await call.answer()
    await state.update_data(auto_send=(call.data == "campaign_mode_auto"))
    data = await state.get_data()
    account = await get_account(data["campaign_account_id"])
    count = await get_users_count()
    lo = account.get("campaign_interval_min_seconds", 300)
    hi = account.get("campaign_interval_max_seconds", 900)
    mode = "автоматическая отправка" if data["auto_send"] else "черновики на проверку"

    await state.set_state(CampaignStates.confirming)
    await call.message.edit_text(
        f"📨 <b>Подтверждение рассылки</b>\n\n"
        f"Контактов в базе: {count}\n"
        f"Режим ответов: {mode}\n"
        f"Интервал между стартом новых диалогов: {lo}-{hi} сек "
        f"(меняется в «Аккаунты → Настройки → Интервал рассылки»)\n\n"
        f"Бот будет писать по одному контакту за раз с этим интервалом, пропуская тех, "
        f"с кем диалог уже есть.",
        parse_mode="HTML", reply_markup=campaign_confirm_kb(),
    )


@router.callback_query(CampaignStates.confirming, F.data == "campaign_start")
async def campaign_confirm_start(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return await call.answer()
    data = await state.get_data()
    account_id = data["campaign_account_id"]
    usernames = await get_all_users()
    ok = campaign.start_campaign(account_id, usernames, data.get("goal"), data.get("auto_send", False))
    await state.clear()
    if not ok:
        return await call.message.edit_text(
            "⚠️ Рассылка для этого аккаунта уже запущена.", reply_markup=campaign_running_kb(account_id),
        )
    await call.message.edit_text(
        f"🚀 <b>Рассылка запущена</b>\n\nВсего в очереди: {len(usernames)}. "
        f"Бот будет постепенно писать людям с заданным интервалом, пропуская тех, с кем "
        f"диалог уже есть.",
        parse_mode="HTML", reply_markup=campaign_running_kb(account_id),
    )


@router.callback_query(F.data.startswith("campaign_stop:"))
async def campaign_stop(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return await call.answer()
    account_id = int(call.data.split(":", 1)[1])
    stopped = campaign.stop_campaign(account_id)
    await call.answer("Рассылка остановлена" if stopped else "Рассылка уже не выполняется")
    await call.message.edit_text(
        "⏸ Рассылка остановлена." if stopped else "Рассылка уже не выполняется.",
        reply_markup=main_menu_kb(True),
    )
