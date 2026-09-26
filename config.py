import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN  = os.getenv("BOT_TOKEN")
ADMIN_IDS  = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]
DB_PATH    = os.getenv("DB_PATH", "parser.db")

# AI dialogue engine (Anthropic Claude) — used to draft/send replies in dialogues.
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()
AI_MODEL          = os.getenv("AI_MODEL", "claude-sonnet-5")

# Web dashboard — single shared password (no per-user accounts, this is a
# personal tool). Unset means the dashboard refuses every request.
WEB_PASSWORD = os.getenv("WEB_PASSWORD", "").strip()
WEB_PORT     = int(os.getenv("PORT", os.getenv("WEB_PORT", "8080")))
