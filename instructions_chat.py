from anthropic import AsyncAnthropic

from config import ANTHROPIC_API_KEY, AI_MODEL
from database import get_account, update_account_profile

_ai_client = AsyncAnthropic(api_key=ANTHROPIC_API_KEY) if ANTHROPIC_API_KEY else None

DOC_MARKER = "###ИНСТРУКЦИИ###"
REPLY_MARKER = "###ОТВЕТ###"

META_SYSTEM_PROMPT = (
    "Ты помогаешь владельцу личного Telegram-аккаунта составить инструкцию для ИИ-ассистента, "
    "который будет вести переписку от его имени с другими людьми. Владелец описывает свободным "
    "текстом: как здороваться, с кем и как общаться, что говорить в разных ситуациях, когда "
    "останавливаться и звать хозяина, любые нюансы стиля.\n\n"
    "Тебе дают текущий документ инструкций (может быть пустым) и новое сообщение владельца. "
    "Собери ОБНОВЛЁННЫЙ полный документ инструкций, вобрав в себя новое сообщение — не просто "
    "припиши его в конец, а органично объедини с уже существующим текстом, устранив противоречия, "
    "если владелец что-то изменил (например, поменял тон общения — замени старое указание на новое, "
    "а не держи оба). Документ должен быть написан как чёткий, связный свод правил, а не диалог.\n\n"
    "Затем напиши короткий дружелюбный ответ владельцу (2-4 предложения): что ты учёл, и если "
    "что-то важное осталось неясным — задай один уточняющий вопрос.\n\n"
    f"Отвечай СТРОГО в этом формате, ничего больше:\n{DOC_MARKER}\n<полный обновлённый документ>\n"
    f"{REPLY_MARKER}\n<короткий ответ владельцу>"
)


def ai_available() -> bool:
    return _ai_client is not None


async def update_instructions(account_id: int, user_message: str) -> dict:
    """Returns {"document": str, "reply": str}."""
    if not _ai_client:
        raise RuntimeError("ANTHROPIC_API_KEY не задан — этот раздел недоступен")

    account = await get_account(account_id) or {}
    current = account.get("custom_instructions") or "(пока пусто)"

    resp = await _ai_client.messages.create(
        model=AI_MODEL, max_tokens=1500, system=META_SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": f"Текущий документ инструкций:\n{current}\n\nНовое сообщение владельца:\n{user_message}",
        }],
    )
    text = "".join(b.text for b in resp.content if b.type == "text").strip()

    document, reply = _parse(text, current, user_message)
    await update_account_profile(account_id, custom_instructions=document, profile_ready=1)
    return {"document": document, "reply": reply}


def _parse(text: str, current: str, user_message: str) -> tuple[str, str]:
    try:
        _, rest = text.split(DOC_MARKER, 1)
        document, reply = rest.split(REPLY_MARKER, 1)
        document, reply = document.strip(), reply.strip()
        if document and reply:
            return document, reply
    except Exception:
        pass
    base = "" if current == "(пока пусто)" else current + "\n\n"
    return base + user_message, "Записал ✅ (не удалось разобрать структурированный ответ ИИ, добавил ваше сообщение как есть)."
