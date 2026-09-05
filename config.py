import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN  = os.getenv("BOT_TOKEN")
ADMIN_IDS  = list(map(int, os.getenv("ADMIN_IDS", "").split(",")))
DB_PATH    = os.getenv("DB_PATH", "parser.db")

# AI dialogue engine (Anthropic Claude) — used to draft/send replies in dialogues.
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()
AI_MODEL          = os.getenv("AI_MODEL", "claude-sonnet-5")
