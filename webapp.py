from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import campaign
import database as db
import dialogue as dlg
import events
import instructions_chat
import userbot as ub
import web_auth
from config import WEB_PASSWORD
from utils import normalize_identifier, resolve_target

app = FastAPI(title="Multiplex")

STATIC_DIR = Path(__file__).parent / "web" / "static"


# ═══════════════════════════════════════════════════════════════════════════════
#  АУТЕНТИФИКАЦИЯ
# ═══════════════════════════════════════════════════════════════════════════════

def require_auth(request: Request):
    if not WEB_PASSWORD:
        raise HTTPException(503, "WEB_PASSWORD не задан на сервере")
    token = request.cookies.get(web_auth.COOKIE_NAME)
    if not web_auth.verify_token(token):
        raise HTTPException(401, "Не авторизован")


class LoginBody(BaseModel):
    password: str


@app.post("/api/login")
async def login(body: LoginBody, response: Response):
    if not WEB_PASSWORD:
        raise HTTPException(503, "WEB_PASSWORD не задан на сервере")
    if not web_auth.check_password(body.password):
        raise HTTPException(401, "Неверный пароль")
    token = web_auth.create_token()
    response.set_cookie(
        web_auth.COOKIE_NAME, token, httponly=True, samesite="lax",
        max_age=web_auth.SESSION_MAX_AGE,
    )
    return {"ok": True}


@app.post("/api/logout")
async def logout(response: Response):
    response.delete_cookie(web_auth.COOKIE_NAME)
    return {"ok": True}


@app.get("/api/me")
async def me(request: Request):
    token = request.cookies.get(web_auth.COOKIE_NAME)
    return {"authenticated": web_auth.verify_token(token)}


# ═══════════════════════════════════════════════════════════════════════════════
#  ХЕЛПЕРЫ СЕРИАЛИЗАЦИИ
# ═══════════════════════════════════════════════════════════════════════════════

async def _serialize_accounts() -> list[dict]:
    accounts = await db.get_accounts()
    contacts = await db.get_all_contacts()
    counts: dict[int, int] = {}
    for c in contacts:
        counts[c["account_id"]] = counts.get(c["account_id"], 0) + 1

    groups: dict[int, list[str]] = {}
    for a in accounts:
        gid = a.get("group_id")
        if gid:
            groups.setdefault(gid, []).append(a["label"])

    out = []
    for a in accounts:
        gid = a.get("group_id")
        linked = [l for l in groups.get(gid, []) if l != a["label"]] if gid else []
        out.append({
            "id": a["id"], "label": a["label"], "phone": a["phone"],
            "connected": bool(a["connected"]),
            "dialogues": counts.get(a["id"], 0),
            "has_instructions": bool(a.get("custom_instructions")),
            "group_id": gid,
            "linked_with": linked,
            "stop_keywords": a.get("stop_keywords"),
            "max_messages_per_dialogue": a.get("max_messages_per_dialogue"),
            "max_messages_per_day": a.get("max_messages_per_day"),
            "work_hours_start": a.get("work_hours_start"),
            "work_hours_end": a.get("work_hours_end"),
            "notify_chat_id": a.get("notify_chat_id"),
            "delay_min_seconds": a.get("delay_min_seconds") or 20,
            "delay_max_seconds": a.get("delay_max_seconds") or 90,
            "campaign_interval_min_seconds": a.get("campaign_interval_min_seconds") or 300,
            "campaign_interval_max_seconds": a.get("campaign_interval_max_seconds") or 900,
            "inactivity_timeout_hours": a.get("inactivity_timeout_hours") or 24,
        })
    return out


def _contact_out(c: dict, account: dict | None) -> dict:
    return {
        "id": c["id"], "identifier": c["identifier"], "display_name": c.get("display_name"),
        "account_id": c["account_id"], "account_label": account["label"] if account else None,
        "status": c["status"], "bucket": c.get("bucket", "active"),
        "auto_send": bool(c["auto_send"]), "ai_enabled": bool(c["ai_enabled"]),
        "goal": c.get("goal"), "created_at": c.get("created_at"),
    }


# ═══════════════════════════════════════════════════════════════════════════════
#  ДАШБОРД
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/api/dashboard", dependencies=[Depends(require_auth)])
async def dashboard():
    accounts = await _serialize_accounts()
    active = await db.get_contacts_by_bucket("active")
    base_counts = await db.get_base_counts()
    return {
        "accounts": accounts,
        "active_dialogues": len(active),
        "messages_today": await db.count_out_messages_today_total(),
        "base_total": await db.get_users_count(),
        "base_unassigned": base_counts["unassigned"],
        "attention_count": len(await db.get_paused_contacts()),
    }


# ═══════════════════════════════════════════════════════════════════════════════
#  АККАУНТЫ
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/api/accounts", dependencies=[Depends(require_auth)])
async def list_accounts():
    return await _serialize_accounts()


class AddAccountBody(BaseModel):
    label: str
    api_id: int
    api_hash: str
    session_string: str


@app.post("/api/accounts", dependencies=[Depends(require_auth)])
async def add_account(body: AddAccountBody):
    result = await ub.connect_account(body.label, body.api_id, body.api_hash, body.session_string)
    if not result.get("ok"):
        raise HTTPException(400, result.get("error", "Не удалось подключить аккаунт"))
    return result


@app.post("/api/accounts/{account_id}/disconnect", dependencies=[Depends(require_auth)])
async def disconnect_account_ep(account_id: int):
    await ub.disconnect_account(account_id)
    return {"ok": True}


@app.post("/api/accounts/{account_id}/reconnect", dependencies=[Depends(require_auth)])
async def reconnect_account_ep(account_id: int):
    ok = await ub.reconnect_account(account_id)
    if not ok:
        raise HTTPException(400, "Не удалось переподключить — возможно, сессия отозвана")
    return {"ok": True}


@app.delete("/api/accounts/{account_id}", dependencies=[Depends(require_auth)])
async def remove_account_ep(account_id: int):
    await ub.remove_account(account_id)
    return {"ok": True}


class SettingsBody(BaseModel):
    stop_keywords: str | None = None
    max_messages_per_dialogue: int | None = None
    max_messages_per_day: int | None = None
    work_hours_start: int | None = None
    work_hours_end: int | None = None
    notify_chat_id: str | None = None
    delay_min_seconds: int | None = None
    delay_max_seconds: int | None = None
    campaign_interval_min_seconds: int | None = None
    campaign_interval_max_seconds: int | None = None
    inactivity_timeout_hours: int | None = None


@app.patch("/api/accounts/{account_id}/settings", dependencies=[Depends(require_auth)])
async def update_settings(account_id: int, body: SettingsBody):
    if not await db.get_account(account_id):
        raise HTTPException(404, "Аккаунт не найден")
    fields = body.model_dump(exclude_unset=True)
    if fields:
        await db.update_account_profile(account_id, **fields)
    return {"ok": True}


# ── инструкции ────────────────────────────────────────────────────────────────

class InstructionMessageBody(BaseModel):
    text: str


@app.get("/api/accounts/{account_id}/instructions", dependencies=[Depends(require_auth)])
async def get_instructions(account_id: int):
    account = await db.get_account(account_id)
    if not account:
        raise HTTPException(404, "Аккаунт не найден")
    return {"content": account.get("custom_instructions") or ""}


@app.post("/api/accounts/{account_id}/instructions", dependencies=[Depends(require_auth)])
async def post_instructions(account_id: int, body: InstructionMessageBody):
    if not await db.get_account(account_id):
        raise HTTPException(404, "Аккаунт не найден")
    if not instructions_chat.ai_available():
        raise HTTPException(400, "ANTHROPIC_API_KEY не настроен на сервере")
    return await instructions_chat.update_instructions(account_id, body.text)


@app.delete("/api/accounts/{account_id}/instructions", dependencies=[Depends(require_auth)])
async def reset_instructions(account_id: int):
    account = await db.get_account(account_id)
    if not account:
        raise HTTPException(404, "Аккаунт не найден")
    if account.get("group_id"):
        await db.propagate_group_instructions(account["group_id"], None)
    else:
        await db.update_account_profile(account_id, custom_instructions=None)
    return {"ok": True}


# ── шаблоны ───────────────────────────────────────────────────────────────────

@app.get("/api/templates", dependencies=[Depends(require_auth)])
async def list_templates():
    return await db.get_templates()


class SaveTemplateBody(BaseModel):
    account_id: int
    name: str


@app.post("/api/templates", dependencies=[Depends(require_auth)])
async def save_template(body: SaveTemplateBody):
    account = await db.get_account(body.account_id)
    if not account or not account.get("custom_instructions"):
        raise HTTPException(400, "У этого аккаунта ещё нет инструкций")
    template_id = await db.create_template(body.name, account["custom_instructions"])
    return {"id": template_id}


@app.post("/api/templates/{template_id}/apply/{account_id}", dependencies=[Depends(require_auth)])
async def apply_template(template_id: int, account_id: int):
    tpl = await db.get_template(template_id)
    if not tpl:
        raise HTTPException(404, "Шаблон не найден")
    account = await db.get_account(account_id)
    if not account:
        raise HTTPException(404, "Аккаунт не найден")
    if account.get("group_id"):
        await db.propagate_group_instructions(account["group_id"], tpl["content"])
    else:
        await db.update_account_profile(account_id, custom_instructions=tpl["content"], profile_ready=1)
    return {"ok": True}


@app.delete("/api/templates/{template_id}", dependencies=[Depends(require_auth)])
async def delete_template_ep(template_id: int):
    await db.delete_template(template_id)
    return {"ok": True}


# ── связка аккаунтов ─────────────────────────────────────────────────────────

class LinkBody(BaseModel):
    account_ids: list[int]


@app.post("/api/accounts/link", dependencies=[Depends(require_auth)])
async def link_accounts(body: LinkBody):
    if len(body.account_ids) < 2:
        raise HTTPException(400, "Нужно минимум 2 аккаунта")
    all_accounts = {a["id"]: a for a in await db.get_accounts()}
    ordered = [all_accounts[i] for i in body.account_ids if i in all_accounts]
    if len(ordered) < 2:
        raise HTTPException(404, "Аккаунты не найдены")

    primary = ordered[0]
    old_group_ids = {a["group_id"] for a in ordered if a.get("group_id")}
    new_group_id = await db.create_account_group()
    for a in ordered:
        await db.set_account_group(a["id"], new_group_id)
    await db.propagate_group_instructions(new_group_id, primary.get("custom_instructions"))
    for gid in old_group_ids:
        await db.dissolve_group_if_alone(gid)
    return {"group_id": new_group_id}


@app.post("/api/accounts/{account_id}/unlink", dependencies=[Depends(require_auth)])
async def unlink_account(account_id: int):
    account = await db.get_account(account_id)
    if not account or not account.get("group_id"):
        raise HTTPException(400, "Аккаунт не связан ни с кем")
    group_id = account["group_id"]
    await db.set_account_group(account_id, None)
    await db.dissolve_group_if_alone(group_id)
    return {"ok": True}


# ═══════════════════════════════════════════════════════════════════════════════
#  ДИАЛОГИ
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/api/dialogues", dependencies=[Depends(require_auth)])
async def list_dialogues(bucket: str = "all"):
    if bucket in ("active", "trash"):
        contacts = await db.get_contacts_by_bucket(bucket)
    else:
        contacts = await db.get_all_contacts()
    accounts = {a["id"]: a for a in await db.get_accounts()}
    return [_contact_out(c, accounts.get(c["account_id"])) for c in contacts]


@app.get("/api/dialogues/{contact_id}", dependencies=[Depends(require_auth)])
async def get_dialogue(contact_id: int):
    c = await db.get_contact(contact_id)
    if not c:
        raise HTTPException(404, "Диалог не найден")
    account = await db.get_account(c["account_id"])
    history = await db.get_dialogue_history(contact_id, limit=50)
    out = _contact_out(c, account)
    out["history"] = [
        {"id": m["id"], "direction": m["direction"], "text": m["text"],
         "status": m["status"], "created_at": m["created_at"]}
        for m in history
    ]
    return out


@app.post("/api/dialogues/{contact_id}/pause", dependencies=[Depends(require_auth)])
async def pause_dialogue(contact_id: int):
    await db.set_contact_status(contact_id, "paused")
    return {"ok": True}


@app.post("/api/dialogues/{contact_id}/resume", dependencies=[Depends(require_auth)])
async def resume_dialogue(contact_id: int):
    await db.set_contact_status(contact_id, "active")
    return {"ok": True}


class ModeBody(BaseModel):
    auto_send: bool


@app.post("/api/dialogues/{contact_id}/mode", dependencies=[Depends(require_auth)])
async def set_mode(contact_id: int, body: ModeBody):
    await db.set_contact_auto_send(contact_id, body.auto_send)
    return {"ok": True}


class BucketBody(BaseModel):
    bucket: str


@app.post("/api/dialogues/{contact_id}/bucket", dependencies=[Depends(require_auth)])
async def set_bucket(contact_id: int, body: BucketBody):
    if body.bucket not in ("active", "trash"):
        raise HTTPException(400, "bucket должен быть active или trash")
    await db.set_contact_bucket(contact_id, body.bucket)
    return {"ok": True}


@app.post("/api/dialogues/{contact_id}/ai_on", dependencies=[Depends(require_auth)])
async def ai_on(contact_id: int):
    await db.set_contact_ai_enabled(contact_id, True)
    return {"ok": True}


@app.post("/api/dialogues/{contact_id}/ignore", dependencies=[Depends(require_auth)])
async def ignore_dialogue(contact_id: int):
    await db.set_contact_ai_enabled(contact_id, False)
    await db.set_contact_status(contact_id, "active")
    return {"ok": True}


class InstructBody(BaseModel):
    text: str


@app.post("/api/dialogues/{contact_id}/instruct", dependencies=[Depends(require_auth)])
async def instruct_dialogue(contact_id: int, body: InstructBody):
    contact = await db.get_contact(contact_id)
    if not contact:
        raise HTTPException(404, "Диалог не найден")
    if not instructions_chat.ai_available():
        raise HTTPException(400, "ANTHROPIC_API_KEY не настроен на сервере")
    result = await instructions_chat.update_instructions(contact["account_id"], body.text)
    outcome = await dlg.retry_after_instruction(contact_id)
    return {"reply": result["reply"], "outcome": outcome}


@app.delete("/api/dialogues/{contact_id}", dependencies=[Depends(require_auth)])
async def delete_dialogue(contact_id: int):
    await db.delete_contact(contact_id)
    return {"ok": True}


class BulkIdsBody(BaseModel):
    ids: list[int]


@app.post("/api/dialogues/bulk_delete", dependencies=[Depends(require_auth)])
async def bulk_delete(body: BulkIdsBody):
    await db.delete_contacts(body.ids)
    return {"ok": True}


@app.post("/api/dialogues/delete_all", dependencies=[Depends(require_auth)])
async def delete_all():
    await db.delete_all_contacts()
    return {"ok": True}


class NewDialogueBody(BaseModel):
    account_id: int
    identifier: str
    display_name: str | None = None
    goal: str | None = None
    opening_text: str | None = None
    use_ai: bool = False


@app.post("/api/dialogues/new", dependencies=[Depends(require_auth)])
async def new_dialogue(body: NewDialogueBody):
    identifier = normalize_identifier(body.identifier)
    client = ub.get_client(body.account_id)
    if not client:
        raise HTTPException(400, "Аккаунт отключён")

    account = await db.get_account(body.account_id)
    opening = body.opening_text
    if body.use_ai:
        if not dlg.ai_available():
            raise HTTPException(400, "ANTHROPIC_API_KEY не настроен на сервере")
        opening = await dlg.generate_opening_message({"goal": body.goal}, account)
    if not opening:
        raise HTTPException(400, "Нужен текст первого сообщения")

    try:
        await client.send_message(resolve_target(identifier), opening)
    except Exception as e:
        raise HTTPException(400, f"Не удалось отправить: {e}")

    contact_id = await db.create_contact(
        account_id=body.account_id, identifier=identifier,
        display_name=body.display_name, goal=body.goal,
    )
    await db.add_dialogue_message(contact_id, "out", opening, status="sent")
    await db.remove_user(identifier)
    events.emit(
        "out", account=account.get("label") if account else None,
        contact=body.display_name or identifier, text=opening,
    )
    return {"contact_id": contact_id, "opening": opening}


# ── черновики ────────────────────────────────────────────────────────────────

@app.get("/api/drafts", dependencies=[Depends(require_auth)])
async def list_drafts():
    drafts = await db.get_pending_drafts()
    out = []
    for d in drafts:
        contact = await db.get_contact(d["contact_id"])
        out.append({
            "id": d["id"], "text": d["text"], "created_at": d["created_at"],
            "contact_id": d["contact_id"],
            "contact_name": (contact.get("display_name") or contact["identifier"]) if contact else "?",
        })
    return out


@app.post("/api/drafts/{message_id}/send", dependencies=[Depends(require_auth)])
async def draft_send(message_id: int):
    draft = await db.get_message(message_id)
    if not draft or draft["status"] != "draft":
        raise HTTPException(400, "Черновик уже обработан")
    contact = await db.get_contact(draft["contact_id"])
    try:
        await dlg.send_text(contact["account_id"], contact["identifier"], draft["text"])
    except Exception as e:
        raise HTTPException(400, f"Ошибка отправки: {e}")
    await db.set_message_status(message_id, "sent")
    return {"ok": True}


class EditDraftBody(BaseModel):
    text: str


@app.post("/api/drafts/{message_id}/edit", dependencies=[Depends(require_auth)])
async def draft_edit(message_id: int, body: EditDraftBody):
    draft = await db.get_message(message_id)
    if not draft or draft["status"] != "draft":
        raise HTTPException(400, "Черновик уже обработан")
    contact = await db.get_contact(draft["contact_id"])
    try:
        await dlg.send_text(contact["account_id"], contact["identifier"], body.text)
    except Exception as e:
        raise HTTPException(400, f"Ошибка отправки: {e}")
    await db.set_message_text(message_id, body.text)
    await db.set_message_status(message_id, "sent")
    return {"ok": True}


@app.post("/api/drafts/{message_id}/reject", dependencies=[Depends(require_auth)])
async def draft_reject(message_id: int):
    await db.set_message_status(message_id, "rejected")
    return {"ok": True}


# ═══════════════════════════════════════════════════════════════════════════════
#  РАССЫЛКА
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/api/campaign", dependencies=[Depends(require_auth)])
async def campaign_status():
    accounts = await db.get_accounts()
    out = []
    for a in accounts:
        assigned = len(await db.get_users_for_account(a["id"]))
        out.append({
            "account_id": a["id"], "label": a["label"], "connected": bool(a["connected"]),
            "assigned": assigned, "running": campaign.is_running(a["id"]),
            "progress": campaign.get_progress(a["id"]),
            "interval_min": a.get("campaign_interval_min_seconds") or 300,
            "interval_max": a.get("campaign_interval_max_seconds") or 900,
        })
    return out


@app.post("/api/campaign/{account_id}/start", dependencies=[Depends(require_auth)])
async def campaign_start(account_id: int):
    usernames = await db.get_users_for_account(account_id)
    if not usernames:
        raise HTTPException(400, "Этому аккаунту не назначено контактов")
    if not campaign.start_campaign(account_id, usernames):
        raise HTTPException(400, "Рассылка для этого аккаунта уже запущена")
    return {"ok": True, "total": len(usernames)}


@app.post("/api/campaign/{account_id}/stop", dependencies=[Depends(require_auth)])
async def campaign_stop(account_id: int):
    return {"stopped": campaign.stop_campaign(account_id)}


# ═══════════════════════════════════════════════════════════════════════════════
#  БАЗА КОНТАКТОВ
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/api/base", dependencies=[Depends(require_auth)])
async def base_overview():
    total = await db.get_users_count()
    counts = await db.get_base_counts()
    accounts = {a["id"]: a["label"] for a in await db.get_accounts()}
    by_account = [
        {"account_id": aid, "label": accounts.get(aid, "?"), "count": n}
        for aid, n in counts["by_account"].items()
    ]
    return {"total": total, "unassigned": counts["unassigned"], "by_account": by_account}


@app.get("/api/base/list", dependencies=[Depends(require_auth)])
async def base_list():
    return await db.get_all_users()


class BaseTextBody(BaseModel):
    text: str


@app.post("/api/base/add", dependencies=[Depends(require_auth)])
async def base_add(body: BaseTextBody):
    usernames = [normalize_identifier(l) for l in body.text.splitlines() if l.strip()]
    new_users = await db.add_users(usernames)
    return {"received": len(usernames), "added": len(new_users), "total": await db.get_users_count()}


@app.post("/api/base/clear", dependencies=[Depends(require_auth)])
async def base_clear():
    await db.clear_users()
    return {"ok": True}


@app.post("/api/base/distribute", dependencies=[Depends(require_auth)])
async def base_distribute():
    accounts = [a for a in await db.get_accounts() if a["connected"]]
    if not accounts:
        raise HTTPException(400, "Нет подключённых аккаунтов")
    result = await db.distribute_unassigned_evenly([a["id"] for a in accounts])
    return {"result": result}


class AssignBody(BaseModel):
    account_id: int
    text: str


@app.post("/api/base/assign", dependencies=[Depends(require_auth)])
async def base_assign(body: AssignBody):
    usernames = [normalize_identifier(l) for l in body.text.splitlines() if l.strip()]
    touched = await db.assign_users_to_account(usernames, body.account_id)
    return {"assigned": len(touched)}


# ═══════════════════════════════════════════════════════════════════════════════
#  ЖИВАЯ АКТИВНОСТЬ (WebSocket)
# ═══════════════════════════════════════════════════════════════════════════════

@app.websocket("/ws/events")
async def ws_events(websocket: WebSocket):
    token = websocket.cookies.get(web_auth.COOKIE_NAME)
    if not web_auth.verify_token(token):
        await websocket.close(code=4401)
        return
    await websocket.accept()
    q = events.subscribe()
    try:
        while True:
            payload = await q.get()
            await websocket.send_json(payload)
    except WebSocketDisconnect:
        pass
    finally:
        events.unsubscribe(q)


# ═══════════════════════════════════════════════════════════════════════════════
#  СТАТИКА (фронтенд)
# ═══════════════════════════════════════════════════════════════════════════════

if STATIC_DIR.exists():
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
