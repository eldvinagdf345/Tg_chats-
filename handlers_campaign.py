from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext

from config import ADMIN_IDS
from database import get_accounts, get_account, get_all_users, get_users_count
from keyboards import main_menu_kb, campaign_choose_account_kb, campaign_confirm_kb, campaign_running_kb
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
            "⚠️ База пуста — сначала загрузите её («📥 Загрузить базу»).", show_alert=True,
        )

    if len(accounts) == 1:
        await _show_confirm(call, accounts[0]["id"], count)
    else:
        await call.message.edit_text(
            f"📨 <b>Рассылка</b>\n\nВ базе {count} контактов. С какого аккаунта начнём?",
            parse_mode="HTML", reply_markup=campaign_choose_account_kb(accounts),
        )


@router.callback_query(F.data.startswith("camp_acc:"))
async def campaign_pick_account(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return await call.answer()
    account_id = int(call.data.split(":", 1)[1])
    count = await get_users_count()
    await _show_confirm(call, account_id, count)


async def _show_confirm(call: CallbackQuery, account_id: int, count: int):
    if campaign.is_running(account_id):
        return await call.message.edit_text(
            "⚠️ У этого аккаунта уже идёт рассылка.",
            reply_markup=campaign_running_kb(account_id),
        )
    account = await get_account(account_id)
    lo = account.get("campaign_interval_min_seconds", 300)
    hi = account.get("campaign_interval_max_seconds", 900)
    await call.message.edit_text(
        f"📨 <b>Подтверждение рассылки</b>\n\n"
        f"Контактов в базе: {count}\n"
        f"Интервал между стартом новых диалогов: {lo}-{hi} сек "
        f"(меняется в «Аккаунты → Настройки → Интервал рассылки»)\n\n"
        f"Стиль и цель общения берутся из инструкций аккаунта. Ответы будут отправляться "
        f"автоматически (можно переключить на черновики в карточке диалога). Если бот "
        f"наткнётся на ситуацию без инструкции — остановится и спросит у вас, что делать. "
        f"Уже начатые диалоги пропускаются.",
        parse_mode="HTML", reply_markup=campaign_confirm_kb(account_id),
    )


@router.callback_query(F.data.startswith("campaign_start:"))
async def campaign_confirm_start(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return await call.answer()
    account_id = int(call.data.split(":", 1)[1])
    usernames = await get_all_users()
    ok = campaign.start_campaign(account_id, usernames)
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
